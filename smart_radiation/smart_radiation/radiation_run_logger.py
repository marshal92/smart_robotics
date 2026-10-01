#!/usr/bin/env python3
"""Static-field experiment logger, ROS 2 Jazzy. No robot commands are sent.

Run --help for options. Requires numpy; record mode also requires sourced ROS.
Field convention: array[row_y, column_x], origin = lower cell boundary,
axis-aligned map frame; nearest containing cell, no image flip.
Start: ros2 service call /radiation_run_logger/start std_srvs/srv/Trigger '{}'
Finish (operator-labelled success/failure, NOT Nav2 action verification):
  ros2 service call /radiation_run_logger/finish std_srvs/srv/SetBool '{data: true}'
One process = one trial. Ctrl-C during a trial marks it interrupted.
Physical field is frozen on startup: not for changing-field experiments.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
import numpy as np


FACTORS = {'nSv/h': .001, 'uSv/h': 1., 'mSv/h': 1000., 'Sv/h': 1e6}


def apply_session(args):
    """Resolve shared settings once, preserving a compact run command."""
    import yaml
    source = Path(args.session).expanduser().resolve()
    cfg = yaml.safe_load(source.read_text())
    if args.method not in cfg['methods'] or args.route not in cfg['routes']:
        raise ValueError('Choose an existing --method and --route from the session YAML')
    def absolute(value):
        p = Path(value).expanduser()
        return str((source.parent / p).resolve() if not p.is_absolute() else p.resolve())
    method = cfg['methods'][args.method]
    route = cfg['routes'][args.route]
    if not isinstance(route.get('goal'), list) or len(route['goal']) != 3 or any(v is None for v in route['goal']):
        raise ValueError('Fill route goal: [x, y, yaw] in the session YAML first')
    for k in ['frame','robot_frame','plan_topic','hz','max_age','max_gap','max_step','real_time','unit']:
        if k in cfg:
            setattr(args, k, cfg[k])
    args.field = absolute(cfg['field'])
    args.meta = absolute(cfg['meta']) if cfg.get('meta') else None
    args.nav_config = absolute(method['nav_config'])
    args.goal = [float(v) for v in route['goal']]
    args.notes = '; '.join(filter(None,[cfg.get('notes',''),method.get('notes',''),args.notes]))
    args.revision = cfg.get('revision',args.revision)
    args.attach = [absolute(v) for v in cfg.get('attach',[])+method.get('attach',[])]
    args.capture_node = method.get('capture_nodes',[])
    args.monitor_name = cfg.get('monitor_names',[]) + method.get('monitor_names',[])
    args.series_root = absolute(cfg['output_root'])
    if args.repeat < 1:
        raise ValueError('--repeat must be >=1')
    if not args.route or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.route):
        raise ValueError('Route ID: letters, digits, underscore or hyphen only')
    args.output = str(Path(args.series_root)/f'{args.route}_{args.method}_{args.repeat:02d}')
    # Freeze both navigation configurations and all declared inputs for the series.
    inputs = [args.field, args.meta or str(Path(args.field).with_name(Path(args.field).stem+'_meta.json'))]
    inputs += [absolute(m['nav_config']) for m in cfg['methods'].values()]
    inputs += [absolute(v) for v in cfg.get('attach',[])]
    inputs += [absolute(v) for m in cfg['methods'].values() for v in m.get('attach',[])]
    args.series_definition = {'settings':cfg, 'sha256':{p:hash_file(p) for p in inputs}}


class ResourceMonitor:
    """Wall-clock sampling; process CPU: 100%=one logical CPU. No ROS-node attribution."""
    def __init__(self, out, names, ros_now, period=1.):
        import psutil
        self.ps = psutil
        self.out, self.names, self.ros_now, self.period = out, set(names), ros_now, period
        self.halt = threading.Event()
        self.thread = None
        self.processes = {}
        self.stats = {}
        self.host = []
        self.found = set()
        self.errors = []
        self.cpus = psutil.cpu_count() or 1

    def discover(self):
        for p in self.ps.process_iter(['pid','name','cmdline','create_time']):
            try:
                # Match executable/script name, never arbitrary ROS parameter arguments.
                cmd = p.info['cmdline'] or []
                labels = {p.info['name'] or ''}
                if cmd:
                    labels.add(Path(cmd[0]).name)
                    if Path(cmd[0]).name.startswith(('python','pypy')) and len(cmd)>1:
                        labels.add(Path(cmd[1]).name)
                        if cmd[1]=='-m' and len(cmd)>2:
                            labels.add(cmd[2].rsplit('.',1)[-1])
                labels |= {v[:-3] for v in list(labels) if v.endswith('.py')}
                matches = labels & self.names
                if p.pid==os.getpid():
                    matches.add('logger_self')
                if not matches:
                    continue
                self.found.update(matches)
                key=(p.pid,p.info['create_time'])
                if key not in self.processes:
                    obj=self.ps.Process(p.pid)
                    obj.cpu_percent(None)  # prime; ignore first meaningless zero
                    self.processes[key]=(obj,'+'.join(sorted(matches)))
            except (self.ps.Error,OSError):
                continue

    def start(self):
        self.thread=threading.Thread(target=self.loop,daemon=True)
        self.thread.start()

    def loop(self):
        try:
            with open(self.out/'resources.csv','w',newline='',buffering=1) as f:
                w=csv.writer(f)
                w.writerow(['wall_unix_s','wall_elapsed_s','ros_s','sim_to_wall_ratio',
                            'kind','pid','process_created_unix_s','label','cpu_percent',
                            'rss_MiB','host_memory_available_MiB','threads'])
                t0=prev_wall=time.monotonic();prev_ros=self.ros_now()
                self.ps.cpu_percent(None)
                self.discover()
                print('Resource monitor matched:',', '.join(sorted(self.found)),flush=True)
                while not self.halt.wait(self.period):
                    wall=time.monotonic();ros=self.ros_now()
                    ratio=(ros-prev_ros)/(wall-prev_wall)
                    cpu=self.ps.cpu_percent(None);self.host.append(cpu)
                    w.writerow([time.time(),wall-t0,ros,ratio,'host','','','host',cpu,'',
                                self.ps.virtual_memory().available/2**20,''])
                    for key,(p,label) in list(self.processes.items()):
                        try:
                            if not p.is_running():
                                del self.processes[key];continue
                            with p.oneshot():
                                pcpu=p.cpu_percent(None);rss=p.memory_info().rss/2**20;threads=p.num_threads()
                            w.writerow([time.time(),wall-t0,ros,ratio,'process',key[0],key[1],label,pcpu,rss,'',threads])
                            s=self.stats.setdefault(str(key),dict(pid=key[0],created=key[1],label=label,cpu=[],rss=[]))
                            s['cpu'].append(pcpu);s['rss'].append(rss)
                        except self.ps.NoSuchProcess:
                            del self.processes[key]
                        except self.ps.Error as e:
                            if str(e) not in self.errors:self.errors.append(str(e))
                    self.discover()
                    prev_wall,prev_ros=wall,ros
        except Exception as e:
            self.errors.append(repr(e))

    def stop(self):
        self.halt.set()
        if self.thread:self.thread.join(timeout=5)
        if self.thread and self.thread.is_alive():
            return {'error':'Resource monitor did not stop; inspect resources.csv'}
        result={'sample_period_wall_s':self.period,'logical_cpus':self.cpus,
                'cpu_scale':'process: 100%=one CPU; host: 100%=all CPUs',
                'not_seen_names':sorted(self.names-self.found),'errors':self.errors,
                'host_cpu_mean_percent':float(np.mean(self.host)) if self.host else None,
                'processes':[],'note':'RSS is per process, shared pages may be counted repeatedly; p95 is descriptive, not a confidence interval. No controller latency measured.'}
        for s in self.stats.values():
            result['processes'].append({k:s[k] for k in ['pid','created','label']} |
                dict(samples=len(s['cpu']),cpu_mean_percent=float(np.mean(s['cpu'])),
                     cpu_p95_percent=float(np.percentile(s['cpu'],95)),rss_peak_MiB=max(s['rss'])))
        save_json(self.out/'resources_summary.json',result)
        return result


def save_json(path, obj):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False))
    temp.replace(path)


def hash_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sample(field, meta, x, y):
    col = math.floor((x - meta['ox']) / meta['res'])
    row = math.floor((y - meta['oy']) / meta['res'])
    if not (0 <= row < field.shape[0] and 0 <= col < field.shape[1]):
        return None
    value = float(field[row, col])
    return value if math.isfinite(value) and value >= 0 else None


class Integral:
    def __init__(self, max_gap, max_step):
        self.max_gap, self.max_step = max_gap, max_step
        self.prev = None
        self.exposure = self.length = self.covered_s = 0.
        self.breaks = 0

    def push(self, t, x, y, dose):
        if dose is None:
            self.prev = None
            self.breaks += 1
            return 'missing_field'
        status = 'first_sample'
        if self.prev is not None:
            pt, px, py, pd = self.prev
            dt, ds = t-pt, math.hypot(x-px, y-py)
            if dt <= 0:
                self.breaks += 1
                status = 'clock_nonmonotonic'
            elif dt > self.max_gap:
                self.breaks += 1
                status = 'gap'
            elif ds > self.max_step:
                self.breaks += 1
                status = 'pose_jump'
            else:
                self.exposure += .5 * (pd+dose) * dt / 3600.
                self.length += ds
                self.covered_s += dt
                status = 'ok'
        self.prev = (t, x, y, dose)
        return status


def self_test():
    f = np.array([[1., 2.], [3., 4.]])
    m = dict(ox=0., oy=0., res=1.)
    assert sample(f, m, -.01, .5) is None
    assert sample(f, m, 1.1, .1) == 2.
    assert sample(f, m, .1, 1.1) == 3.
    a = Integral(2., 10.)
    a.push(0., 0., 0., 3600.)
    a.push(1., 1., 0., 3600.)
    assert a.exposure == 1. and a.length == 1.
    assert a.push(5., 2., 0., 3600.) == 'gap'
    assert a.exposure == 1.
    a.push(6., 2., 0., None)
    a.push(7., 2., 0., 3600.)
    assert a.exposure == 1.
    a.push(8., 2., 0., 3600.)
    assert a.exposure == 2.
    assert a.push(9., 20., 0., 3600.) == 'pose_jump'
    assert FACTORS['mSv/h'] == 1000.
    print('PASS: units, grid indexing, integral, gaps, jumps. ROS not tested.')


def prepare(args):
    source = Path(args.field).expanduser().resolve()
    meta_source = Path(args.meta).expanduser().resolve() if args.meta else source.with_name(source.stem + '_meta.json')
    meta = json.loads(meta_source.read_text())
    for k in ('ox', 'oy', 'res'):
        if k not in meta or not math.isfinite(float(meta[k])):
            raise ValueError('Metadata must explicitly contain finite ox, oy, res')
        meta[k] = float(meta[k])
    if meta['res'] <= 0:
        raise ValueError('Metadata resolution must be positive')
    raw = np.load(source, allow_pickle=False)
    if raw.ndim != 2 or raw.size == 0 or not np.issubdtype(raw.dtype, np.number):
        raise ValueError('Expected nonempty numeric 2D field')
    if not np.all(np.isfinite(raw)) or np.any(raw < 0):
        raise ValueError('Static reference field must contain finite nonnegative values')
    field = raw.astype(float) * FACTORS[args.unit]
    if not np.all(np.isfinite(field)):
        raise ValueError('Overflow converting dose units')
    # All required input files validated before creating the trial directory.
    config = Path(args.nav_config).expanduser().resolve()
    if not config.is_file():
        raise ValueError('Nav2 config not found')
    attachments = [Path(f).expanduser().resolve() for f in args.attach]
    if any(not f.is_file() for f in attachments):
        raise ValueError('One of the --attach files was not found')
    out = Path(args.output).expanduser().resolve()
    shared = None
    if getattr(args,'series_root',None):
        root=Path(args.series_root)
        root.mkdir(parents=True,exist_ok=True)
        definition=json.loads(json.dumps(args.series_definition))
        definition_file=root/'series.json'
        if definition_file.exists():
            if json.loads(definition_file.read_text())!=definition:
                raise ValueError('Series settings/input files changed. Set a NEW output_root in session YAML.')
        else:
            save_json(definition_file,definition)
        shared=root/'shared';shared.mkdir(exist_ok=True)
    out.mkdir(parents=True, exist_ok=False)
    run_args={k:v for k,v in vars(args).items() if k!='series_definition'}
    manifest = {'logger_version': 2, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'arguments': run_args, 'platform': platform.platform(),
                'ros_distro': os.environ.get('ROS_DISTRO'),
                'position_source': 'TF localization, not Gazebo ground truth',
                'field_shape': list(raw.shape), 'metadata': meta,
                'sampling': 'containing cell; no axis rotation or image flip',
                'exposure_unit': 'uSv', 'field_time_model': 'static, frozen at startup',
                'boundaries': 'manual services; finish success is operator-labelled',
                'files': {}, 'parameter_snapshots': [], 'state': 'prepared'}
    files = [(source, 'reference_field.npy'), (meta_source, 'reference_meta.json'),
             (config, 'nav2_input.yaml'), (Path(__file__).resolve(), 'logger_used.py')]
    files += [(f, f'attachment_{i:02d}_{f.name}') for i, f in enumerate(attachments)]
    for src, name in files:
        digest=hash_file(src)
        destination=(shared/(digest+src.suffix)) if shared else out/name
        if not destination.exists():shutil.copy2(src,destination)
        elif hash_file(destination)!=digest:raise ValueError('Saved shared input is corrupted: '+str(destination))
        manifest['files'][name] = {'source': str(src), 'sha256': digest,
                                  'path':os.path.relpath(destination,out)}
    nodes = list(dict.fromkeys(['/planner_server', '/controller_server',
                               '/global_costmap/global_costmap', '/local_costmap/local_costmap',
                               '/velocity_smoother'] + args.capture_node))
    for i, node in enumerate(nodes):
        print('Capturing parameters:', node, flush=True)
        info = {'node': node}
        try:
            r = subprocess.run(['ros2', 'param', 'dump', node], capture_output=True,
                               text=True, timeout=6, check=False)
            name = f'params_{i:02d}.yaml'
            if r.returncode == 0 and r.stdout.strip():
                import yaml
                parsed=yaml.safe_load(r.stdout)
                if not isinstance(parsed,dict):raise ValueError('Invalid parameter dump')
                canonical=yaml.safe_dump(parsed,sort_keys=True)
                digest=hashlib.sha256(canonical.encode()).hexdigest()
                destination=shared/(digest+'.yaml') if shared else out/name
                if not destination.exists():destination.write_text(canonical)
                info.update(status='captured', file=os.path.relpath(destination,out),sha256=digest)
            else:
                info.update(status='failed', error=r.stderr or r.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as e:
            info.update(status='failed', error=str(e))
        manifest['parameter_snapshots'].append(info)
    save_json(out / 'passport.json', manifest)
    return field, meta, out, manifest


def record(args):
    import rclpy
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.time import Time
    from tf2_ros import Buffer, TransformListener, TransformException
    from std_srvs.srv import Trigger, SetBool
    from nav_msgs.msg import Path as NavPath
    import psutil  # fail before creating a run if monitoring dependency is missing

    field, meta, out, passport = prepare(args)
    rclpy.init(args=[])

    class Logger(Node):
        def __init__(self):
            super().__init__('radiation_run_logger', parameter_overrides=[
                Parameter('use_sim_time', value=not args.real_time)])
            self.buffer = Buffer()
            self.listener = TransformListener(self.buffer, self)
            self.active = self.finished = False
            self.start_ros = self.start_wall = None
            self.integral = Integral(args.max_gap, args.max_step)
            self.last_stamp = None
            self.bad = self.rows = 0
            self.last_report = time.monotonic()
            self.resources = ResourceMonitor(out,args.monitor_name,self.now)
            self.csvf = open(out / 'samples.csv', 'w', newline='', buffering=1)
            self.writer = csv.writer(self.csvf)
            self.writer.writerow(['t_ros_s','t_elapsed_s','tf_stamp_s','tf_age_s',
                                  'x_map_m','y_map_m','yaw_rad','dose_rate_uSv_h',
                                  'exposure_valid_uSv','path_valid_m','covered_s','status'])
            self.eventf = open(out / 'events.jsonl', 'w', buffering=1)
            self.pathf = open(out / 'plans.jsonl', 'w', buffering=1)
            self.start_srv = self.create_service(Trigger, '~/start', self.start)
            self.end_srv = self.create_service(SetBool, '~/finish', self.finish)
            self.path_sub = self.create_subscription(NavPath, args.plan_topic, self.plan, 10)
            self.timer = self.create_timer(1./args.hz, self.tick)
            self.get_logger().info(f'READY: {out}. Waiting for /radiation_run_logger/start')

        def now(self):
            return self.get_clock().now().nanoseconds / 1e9

        def event(self, kind, **details):
            self.eventf.write(json.dumps(dict(event=kind, t_ros_s=self.now(),
                                             wall_unix_s=time.time(), **details)) + '\n')

        def pose(self):
            t = self.buffer.lookup_transform(args.frame, args.robot_frame, Time())
            stamp = t.header.stamp.sec + t.header.stamp.nanosec / 1e9
            age = self.now()-stamp
            if stamp <= 0 or age < -.05 or age > args.max_age:
                raise ValueError('stale_or_future_TF')
            p, q = t.transform.translation, t.transform.rotation
            vals = [p.x,p.y,q.x,q.y,q.z,q.w]
            if not all(math.isfinite(v) for v in vals):
                raise ValueError('nonfinite_TF')
            yaw = math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
            return stamp, age, p.x, p.y, yaw

        def start(self, req, resp):
            if self.active or self.finished:
                resp.success, resp.message = False, 'One process = one trial; restart logger.'
                return resp
            try:
                _, _, x, y, yaw = self.pose()
                if sample(field, meta, x, y) is None:
                    raise ValueError('Robot is outside reference field')
            except (TransformException, ValueError) as e:
                resp.success, resp.message = False, str(e)
                return resp
            self.start_ros, self.start_wall = self.now(), time.monotonic()
            self.active = True
            self.resources.start()
            passport.update(state='recording', measured_start=[x,y,yaw], start_ros_s=self.start_ros)
            save_json(out / 'passport.json', passport)
            self.event('start')
            self.tick()
            resp.success, resp.message = True, 'Recording. Send navigation goal now.'
            return resp

        def finish(self, req, resp):
            if not self.active:
                resp.success, resp.message = False, 'No active trial'
                return resp
            self.tick()
            self.stop('operator_success' if req.data else 'operator_failure')
            resp.success, resp.message = True, str(out / 'summary.json')
            return resp

        def plan(self, msg):
            if not self.active:
                return
            self.pathf.write(json.dumps({'received_ros_s':self.now(),
                'frame':msg.header.frame_id,
                'stamp_s':msg.header.stamp.sec+msg.header.stamp.nanosec/1e9,
                'xy':[[p.pose.position.x,p.pose.position.y] for p in msg.poses]})+'\n')

        def tick(self):
            if not self.active:
                return
            now = self.now()
            if now < self.start_ros:
                self.stop('clock_reset')
                return
            try:
                stamp, age, x, y, yaw = self.pose()
                if self.last_stamp is not None and stamp < self.last_stamp:
                    self.stop('tf_time_reset')
                    return
                if stamp == self.last_stamp:
                    return
                self.last_stamp = stamp
                dose = sample(field, meta, x, y)
                # Do not integrate measurements timestamped before manual start.
                if stamp < self.start_ros:
                    return
                status = self.integral.push(stamp,x,y,dose)
                row = [now,now-self.start_ros,stamp,age,x,y,yaw,
                       '' if dose is None else dose]
            except (TransformException, ValueError) as e:
                self.integral.prev = None
                status = 'invalid_TF'
                self.event(status, detail=str(e))
                row = [now,now-self.start_ros,'','','','','','']
            if status not in ('ok','first_sample'):
                self.bad += 1
            self.rows += 1
            self.writer.writerow(row + [self.integral.exposure,self.integral.length,
                                         self.integral.covered_s,status])
            if time.monotonic()-self.last_report >= 5:
                self.last_report = time.monotonic()
                self.get_logger().info(f'T={now-self.start_ros:.1f}s; '
                    f'L(valid)={self.integral.length:.2f}m; E(valid)={self.integral.exposure:.3f}uSv; '
                    f'covered={self.integral.covered_s:.1f}s; bad_rows={self.bad}')

        def stop(self, result):
            if not self.active:
                return
            duration = self.now()-self.start_ros
            self.active, self.finished = False, True
            self.event('finish', result=result)
            resources_summary=self.resources.stop()
            s = dict(result=result, duration_ros_s=duration,
                     duration_wall_s=time.monotonic()-self.start_wall,
                     exposure_valid_uSv=self.integral.exposure,
                     path_valid_m=self.integral.length, covered_s=self.integral.covered_s,
                     coverage_fraction=self.integral.covered_s/duration if duration>0 else None,
                     bad_rows=self.bad, interval_breaks=self.integral.breaks, rows=self.rows,
                     resources_file='resources_summary.json',
                     resource_errors=resources_summary.get('errors',[]),
                     note='Valid-interval estimate only. Inspect gaps, TF quality, boundaries and field alignment; no automatic Nav2 success verification.')
            save_json(out / 'summary.json',s)
            passport.update(state='finished', result=result)
            save_json(out / 'passport.json',passport)
            self.csvf.flush(); self.pathf.flush(); self.eventf.flush()
            self.get_logger().info(json.dumps(s))

    node = Logger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop('interrupted')
        node.csvf.close(); node.pathf.close(); node.eventf.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--session',help='YAML containing common settings, two methods and routes')
    p.add_argument('--repeat',type=int,default=1)
    p.add_argument('--monitor-name',action='append',default=[],help='Process executable/script basename (not ROS node name); repeatable')
    p.add_argument('--field', help='Original physical .npy, not normalized costmap')
    p.add_argument('--meta', help='Defaults to FIELD_meta.json; requires ox,oy,res')
    p.add_argument('--unit', choices=FACTORS, help='Explicit units stored in .npy')
    p.add_argument('--nav-config')
    p.add_argument('--method', choices=['baseline','proposed'])
    p.add_argument('--route')
    p.add_argument('--goal', nargs=3, type=float, metavar=('X','Y','YAW'))
    p.add_argument('--output', help='New, nonexisting trial directory')
    p.add_argument('--notes', default='')
    p.add_argument('--attach', action='append', default=[], help='Copy extra source/config/geometry files into passport; repeatable')
    p.add_argument('--revision', default='not_recorded', help='Robot project commit/version')
    p.add_argument('--capture-node', action='append', default=[], help='Additional ROS node parameter dump; repeatable')
    p.add_argument('--frame', default='map')
    p.add_argument('--robot-frame', default='base_footprint')
    p.add_argument('--plan-topic', default='/plan')
    p.add_argument('--hz', type=float, default=10.)
    p.add_argument('--max-gap', type=float, default=.5)
    p.add_argument('--max-age', type=float, default=.5)
    p.add_argument('--max-step', type=float, default=1., help='Pose discontinuity limit in meters per sample')
    p.add_argument('--real-time', action='store_true', help='Hardware only; otherwise use_sim_time=true')
    args = p.parse_args()
    if args.self_test:
        self_test(); return
    if args.session:
        try:apply_session(args)
        except (ValueError,KeyError,TypeError,OSError) as e:p.error(str(e))
    if not args.monitor_name:
        args.monitor_name=['planner_server','controller_server','component_container','component_container_isolated',
                           'radiation_field_server','baseline_field_server','radiation_mapper','virtual_geiger']
    for name in ('field','unit','nav_config','method','route','goal','output'):
        if getattr(args,name) is None:
            p.error('--'+name.replace('_','-')+' is required')
    if args.unit not in FACTORS:p.error('Unsupported field unit')
    for val in [args.hz,args.max_gap,args.max_age,args.max_step,*args.goal]:
        if not math.isfinite(val):
            p.error('Numeric arguments must be finite')
    if min(args.hz,args.max_gap,args.max_age,args.max_step)<=0:
        p.error('Rates and thresholds must be positive')
    record(args)


if __name__ == '__main__':
    main()
