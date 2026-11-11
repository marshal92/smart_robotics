# Журнал змін кодової бази (Changelog)

Короткий реєстр внесених змін у кодову базу проєкту із зазначенням дати, змінених компонентів та технічного обґрунтування.

---

## [2026-11-09]

### 1. `smart_plugins` / `smart_control` / `smart_ai`: Переведення `nav_coordinator` на C++ та усунення вразливостей обробників `SmartCommand`
* **Файли:**
  * `smart_plugins/src/nav_coordinator.cpp` *(новий C++ вузол)*
  * `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml`
  * `smart_control/launch/control_core.launch.py`
  * `smart_control/smart_control/nav_coordinator.py`
  * `smart_control/smart_control/waypoint_manager.py`
  * `smart_control/smart_control/tactical_executor.py`
  * `smart_ai/smart_ai/spatial_projector_node.py`
* **Що змінено:**
  1. **Переписано `nav_coordinator` на C++ (`smart_plugins/src/nav_coordinator.cpp`):**
     * Повністю перенесено логіку Sliding Window (`NavigateThroughPoses` / `NavigateToPose`), черги завдань, `LAPS`, накопичувача маршрутів (`add_to_route`/`start_route`) та збереження стану для `RESUME` з Python (`BasicNavigator` із двома вузлами та постійним `spin_once`) на нативний асинхронний `rclcpp_action::Client`.
     * Переключено запуск у `control_core.launch.py` на C++ бінарник `smart_plugins/nav_coordinator` (Python-версію у `smart_control` також оновлено й залишено як резерв).
  2. **Захист від некоректного JSON та невалідних структур даних:**
     * У `nav_coordinator` (C++ та Python) і `tactical_executor.py` при помилці парсингу JSON або якщо `payload` не є JSON-об'єктом, команда негайно відхиляється (`return`) без запуску руху за замовчуванням у `(0, 0)` або на `1.0 м` вперед.
     * Додано перевірку наявності обов'язкових координат (`x`, `y`), скінченності чисел (`std::isfinite` / `math.isfinite`), формату масиву `points` та верхніх меж (`laps` до `100`, `points` до `500`).
  3. **Фільтрація адресата у `waypoint_manager.py` до розбору JSON:**
     * Перевірка `msg.target_system in ('waypoints', 'nav')` виконується на початку `command_cb` до звернення до полів `payload`, щоб сторонні команди не викликали `AttributeError`.
  4. **Безпечна обробка `cancel`, `rth` та `resume`:**
     * Використано прапорець `cancel_requested` замість елемента черги `nav_queue`, який раніше міг стиратися при швидкому виклику `cancel` + `rth`. Тепер `rth` завжди скасовує активну ціль Nav2 перед стартом повернення на базу.
     * `resume` відхиляється у станах `WARNING` та `EVACUATING`, а виконання відновленого завдання з черги очікує переходу FSM у `NORMAL` / `DISABLED`.
  5. **Узгодження стоп-команд для `tactical_executor` та `smart_ai`:**
     * `tactical_executor.py` тепер миттєво зупиняє рух при отриманні глобальних команд `system:stop`, `system:start_freeride`, `system:restart`, а також `nav:cancel` і `nav:rth` (від `safety_watchdog`).
     * У `spatial_projector_node.py` при виявленні об'єкта під час пошуку відправляється `tactical:stop` замість глобального `system:stop`.
* **Пояснення / Причина:**
  * Переведення `nav_coordinator` на C++ усуває накладні витрати Python-інтерпретатора та подвійного `spin_once` на кожній ітерації циклу, а валідація `SmartCommand` гарантує безпечну поведінку робота при аварійних переходах FSM та нештатних вхідних даних.

---

### 2. `smart_radiation_plugins` / `smart_plugins` / `smart_radiation` / `web_ui_2.0`: Виділення C++ плагінів радіації, конфігурація порогів та управління віртуальним дозиметром із веб-інтерфейсу
* **Файли:**
  * `smart_radiation_plugins/*` *(новий пакет: `radiation_layer.cpp`, `radiation_mapper_node.cpp`, `virtual_geiger_node.cpp`, `alara_speed_reflex.cpp`)*
  * `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml` *(залишено лише `telemetry_mux` та `stabilized_frame_publisher_node`)*
  * `smart_radiation/config/radiation_params.yaml` *(новий конфіг)*
  * `smart_radiation/smart_radiation/radiation_field_server.py`, `smart_radiation/smart_radiation/radiation_manager.py`, `smart_radiation/smart_radiation/view_map.py`, `smart_radiation/smart_radiation/generate_map.py`, `smart_radiation/smart_radiation/ground_truth_logger.py`
  * `smart_radiation/launch/radiation_bringup.launch.py`, `smart_radiation/setup.py`, `smart_radiation/package.xml`
  * `smart_nav/config/nav2_params.yaml`, `smart_nav/package.xml`
  * `Infrastructure_as_Code /web_ui_2.0/src/components/teleop/TeleopTabs.vue`
* **Що змінено:**
  1. **Виділено пакет `smart_radiation_plugins`:** Усі радіаційні C++ компоненти (`smart_radiation_plugins::RadiationLayer`, `radiation_mapper_node`, `virtual_geiger_node`, `alara_speed_reflex_node`) винесено зі `smart_plugins` в окремий пакет `smart_radiation_plugins` за зразком `Asymmetric-radiation`. У `RadiationLayer` додано параметр `max_cost` ($C_{\max}$, за замовчуванням `220`), який винесено в `smart_nav/config/nav2_params.yaml`. У `smart_plugins` залишилися виключно системні вузли робота (`telemetry_mux`, `stabilized_frame_publisher_node`).
  2. **Синхронізація з `Asymmetric-radiation`, відновлення `radiation_map.npy` та очищення шляхів:** Відновлено еталонну карту `radiation_map.npy` (`800x1200`), яка раніше була перезаписана старим маппером зі зміщенням рядків (`800x800`). У `view_map.py` масштаб штрафу приведено до `220`, прибрано жорсткі заміни шляхів `install/... -> src/smart_robotics/...`.
  3. **Динамічні пороги та конфіг `radiation_params.yaml`:** Параметри `d_noise`, `d_crit`, `k` у `radiation_field_server.py` оголошено динамічними параметрами ROS 2 (з миттєвим перерахунком карти при зміні через `ros2 param set`) і винесено в `smart_radiation/config/radiation_params.yaml`, який автоматично підвантажується в `radiation_bringup.launch.py`.
  4. **Керування віртуальним дозиметром за командою (`rad_geiger_on` / `rad_geiger_off`):** Ввімкнення поля (`rad_on`) більше не запускає `virtual_geiger` примусово. Віртуальний дозиметр вмикається та вимикається окремими кнопками (`Virt Geiger ON` / `Virt Geiger OFF`), що виключає конфлікти при підключенні фізичного датчика до `/radiation/dose`.
  5. **Оновлення веб-інтерфейсу (`TeleopTabs.vue`):** Кнопки `Rad Map ON` / `Rad Map OFF` перенесено з вкладки `Manager` у вкладку `Radiation`, додано кнопки `Virt Geiger ON`, `Virt Geiger OFF` та `Rad Stop`.
* **Пояснення / Причина:**
  * Забезпечено повну структурну готовність `smart_radiation` + `smart_radiation_plugins` до виносу в окремий репозиторій, зручне налаштування порогів без навантаження на шину телеметрії та безконфліктне перемикання між віртуальним і фізичним дозиметрами.

---

### 2. `smart_radiation` / `smart_control` / `smart_master` / `smart_plugins`: Ізоляція та модульність радіаційної підсистеми
* **Файли:**
  * `smart_radiation/smart_radiation/radiation_manager.py` *(новий вузол)*
  * `smart_radiation/launch/radiation_bringup.launch.py`, `smart_radiation/setup.py`
  * `smart_radiation/smart_radiation/radiation_field_server.py`, `smart_radiation/smart_radiation/baseline_field_server.py`
  * `smart_plugins/src/radiation_mapper_node.cpp`, `smart_plugins/src/virtual_geiger_node.cpp`
  * `smart_control/smart_control/mission_manager.py`
  * `smart_master/launch/sim_master.launch.py`, `smart_master/launch/real_master.launch.py`
  * `Infrastructure_as_Code /autostart/start_server.sh`, `Infrastructure_as_Code /autostart/start_robot.sh`
* **Що змінено:**
  1. **Вимкнено автозапуск радіації:** Видалено `radiation_bringup` із `sim_master.launch.py` та `real_master.launch.py` (`sim_master_asym` та `sim_master_baseline` збережено).
  2. **Інкапсуляція логіки у `radiation_manager`:** З `mission_manager.py` видалено всі внутрішні клієнти сервісів (`/radiation_mapper`, `/radiation_field_server`, `/virtual_geiger`) та шляхи до `.npy` / `/dev/shm`. Управління командами (`rad_on`, `rad_off`, `rad_load:<name>`, `rad_record:<name>`, `rad_save`, `rad_stop`, `rad_clear`) перенесено у `radiation_manager.py`.
  3. **Запуск підсистеми за командою (`rad_on` / `rad_start`):** `mission_manager` при першому натисканні `rad_on` у веб-інтерфейсі (або команді `rad_start`) піднімає `radiation_bringup.launch.py` в окремій сесії `radiation_session` без перезапуску SLAM/Nav2 та без дублювання процесів. При подальших командах `rad_off` / `rad_on` вузол `radiation_manager` присипляє та будить вузли радіації.
  4. **Управління картою датчика (`virtual_geiger`), єдиний `maps_dir` та захист від конфліктів:**
     * Усі вузли використовують єдиний параметр `maps_dir` (`~/ros2_ws/src/smart_robotics/smart_radiation/maps`).
     * При `rad_load:<name>` (якщо `<name> != explored_map.npy` і не задано ручний оверрайд через `rad_source:<name>`) синхронно оновлюється і поле costmap, і карта `virtual_geiger`. При `rad_record:explored_map.npy` запис ведеться в `explored_map.npy`, а `virtual_geiger` продовжує читати еталонне поле (`sensor_map_path`, за замовчуванням `radiation_map_complex.npy`).
     * У `virtual_geiger_node.cpp` додано перевірку `count_publishers("/radiation/dose") > 1` (автоматичне заглушення при підключенні фізичного дозиметра або дублікаті вузла), а в `mission_manager.py` — перевірку графа ROS 2 (`get_node_names()`) перед запуском `radiation_session`.
  5. **Виправлення завантаження ваг у C++ маппері:** При завантаженні карти іншого розміру без файлу ваг масив `weight_grid_` створюється строго за розміром нової карти з перевіркою сумісності.
  6. **Публікація статусу `/radiation/status`:** Зворотний зв'язок про готовність, активну карту, запис і помилки після фактичного виконання сервісів.
* **Пояснення / Причина:**
  * Досягнуто повної модульності: `smart_control` відповідає виключно за запуск підсистеми як чорної скриньки, а вся логіка роботи з радіаційними картами, дозиметром і штрафами ізольована всередині `smart_radiation`.

---

### 2. `smart_control`: Забезпечення нульового споживання ресурсів у стані очікування (Zero-Idle) та усунення колізій у `tactical_executor`
* **Файли:**
  * `smart_control/smart_control/tactical_executor.py`
* **Що змінено:**
  1. У режимі `IDLE` активна підписка виключно на `/smart_command` (підписки на `/odom`, `/scan` і таймери знищені — 0.0% CPU).
  2. Додано Watchdog-таймер (0.5 с) для `track_target` і таймаути безпеки для `move_relative` / `turn_relative`.
  3. Кешування індексів променів лідара ($\pm 20^\circ$) та миттєва зупинка в `scan_cb`.
  4. Топік статусу переведено з `/smart_telemetry` на `/tactical/status` (`std_msgs/msg/String`).
* **Пояснення / Причина:**
  * Усунуто колізію DDS із `telemetry_mux` та гарантовано нульове споживання ресурсів Raspberry Pi у фоновому режимі.

---

## [2026-11-09] — Міграція `nav_coordinator` та вузлів керування маніпулятором (`teleop_manager`, `tactical_server`, `control_hub`) на C++ (Zero-Idle)

### 1. `smart_plugins`, `smart_control`, `smart_ai`: Переписування `nav_coordinator` на C++ та виправлення обробників `SmartCommand`
* **Файли:**
  * `smart_plugins/src/nav_coordinator.cpp`, `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml`
  * `smart_control/launch/control_core.launch.py`, `smart_control/smart_control/nav_coordinator.py`
  * `smart_control/smart_control/waypoint_manager.py`, `smart_control/smart_control/tactical_executor.py`
  * `smart_ai/smart_ai/spatial_projector_node.py`
* **Що змінено:**
  1. Створено C++ вузол `nav_coordinator` у пакеті `smart_plugins` із прямою роботою з Action-серверами Nav2 (`/compute_path_to_pose`, `/follow_path`, `/navigate_to_pose`, `/spin`) без Python-прошарку `BasicNavigator`.
  2. Усунено помилки маршрутизації `SmartCommand` (`start_patrol`, `set_goal`, `delete_route`, `track_target`, `move_relative`, ініціалізація `target_class`).

---

### 2. `manipulator_control`, `smart_moveit_config`: Переписування `teleop_manager`, `tactical_server`, `control_hub` на C++ (Zero-Idle) та актуалізація робочої зони (+X)
* **Файли:**
  * `manipulator_control/src/teleop_manager.cpp`, `manipulator_control/src/tactical_server.cpp`, `manipulator_control/src/control_hub.cpp`
  * `manipulator_control/CMakeLists.txt`, `manipulator_control/package.xml`
  * `manipulator_control/launch/auto_control.launch.py`, `manipulator_control/manipulator_control/test/square_horizontal.csv`
  * `smart_moveit_config/config/smart_robot.srdf`
* **Що змінено:**
  1. **`teleop_manager.cpp` (Zero-Idle):** Таймер 50 Гц запускається лише під час руху й вимикається в простої (`servo_timer_->cancel()`); опитування TF виконується лише за наявності підписників на `/web_teleop/tool_pose`; додано Watchdog-таймаут 10 с та блокування `unfold` у режимі `AUTO`.
  2. **`tactical_server.cpp`:** Нативний C++ Action-сервер `manipulator_action` (обгортка над `/move_action`, `/compute_cartesian_path`, `/execute_trajectory`) без поллінгу `time.sleep` та GIL-блокувань.
  3. **`control_hub.cpp` (Zero-Idle):** Повністю прибрано підписку на `/tf` (`TransformListener`) — початкова поза інструмента обчислюється через `/compute_fk` лише в момент запуску завдання; реалізовано RAII-захист прапора `is_executing_`.
  4. **Конфігурація та координати:** Виправлено `virtual_joint` (`child_link="base_footprint"`) і матрицю колізій у `smart_robot.srdf`, оновлено `auto_control.launch.py` та координати шаблону `square_horizontal.csv` під вісь `+X`.
* **Пояснення / Причина:**
  * Усунено навантаження ~207% CPU у стані очікування від трьох Python-вузлів маніпулятора при збереженні повної сумісності з усіма launch-файлами та веб-інтерфейсами.

---

### 3. `smart_plugins`, `manipulator_control`, `smart_server`, `smart_master`: C++ `trajectory_bridge`, єдиний серверний лаунч `arm_backend.launch.py`, керування з веб-інтерфейсу через `twin_orchestrator` та правила Zenoh
* **Файли:**
  * `smart_plugins/src/trajectory_bridge.cpp`, `manipulator_control/src/trajectory_bridge.cpp`
  * `smart_plugins/CMakeLists.txt`, `smart_plugins/package.xml`, `manipulator_control/CMakeLists.txt`
  * `smart_server/launch/arm_backend.launch.py`, `smart_server/launch/server.launch.py`, `smart_server/smart_server/twin_orchestrator.py`
  * `smart_master/launch/real_master.launch.py`
  * `Infrastructure_as_Code /autostart/start_robot.sh`, `Infrastructure_as_Code /autostart/start_server.sh`
  * `Infrastructure_as_Code /web_ui_2.0/src/components/teleop/ArmControl.vue`
* **Що змінено:**
  1. **C++ `trajectory_bridge` (Action + Topic):** Створено C++ вузол у `smart_plugins` та `manipulator_control`, який підтримує і Action `/arm_controller/follow_joint_trajectory` (із миттєвим перериванням при Cancel), і топік `/arm_controller/joint_trajectory` (для повзунків `ArmControl.vue`, кнопки `Unfold` та `moveit_servo`). Підключено до `real_master.launch.py` за умовою `use_arm:=true`.
  2. **Єдиний лаунч `arm_backend.launch.py` (для Sim та Real без RViz):** Інтегровано `move_group` безпосередньо в `arm_backend.launch.py` з автоматичною передачею `use_sim_time` (`true` або `false`); `rviz2` за замовчуванням вимкнено (`use_rviz:=false`).
  3. **Керування стеком маніпулятора через `twin_orchestrator`:** Додано обробку команд `arm_on`, `arm_on_rviz`, `arm_off` у `twin_orchestrator.py` (запуск/зупинка `arm_backend.launch.py` у `tmux`-сесії `arm_session` на сервері) та кнопки `MoveIt ON` / `MoveIt OFF` / `Unfold` у вкладку `Arm` веб-інтерфейсу `web_ui_2.0`.
  4. **Zenoh Bridge:** Додано правила `--allow` для `^rt/arm_joint_states$`, `^rt/arm_controller/joint_trajectory$` та `^.*/arm_controller/follow_joint_trajectory/.*$` у `start_robot.sh` та `start_server.sh`.
  5. **Єдиний нативний лаунчер (`smart_launcher.py`) та очищення дублів:**
     * Створено PyQt6 + `QWebEngineView` операторський лаунчер (`Infrastructure_as_Code /autostart/smart_launcher.py` та `~/smart_launcher.py`) із підтримкою режимів `Simulation` та `Real Robot`, автопошуком карт `.sdf` та вбудованим веб-дашбордом.
     * У `start_robot.sh` та `start_server.sh` додано прийом аргументу `USE_ARM=${1:-false}` і передачу `use_arm` у `real_master.launch.py` та `server.launch.py`.
     * Видалено застарілі лаунчі `moveit_client.launch.py`, `moveit_real_client.launch.py`, `arm_moveit_sim.launch.py` із `smart_server/launch/`.
     * Усі коментарі та лог-повідомлення приведено до англійської мови.
  6. **Ергономіка інтерфейсу лаунчера (Fullscreen & Collapsible Bar):**
     * Додано згортання верхньої панелі управління за допомогою кнопки `▲ Hide Bar (F10)` та клавіші `F10`. При прихованій панелі в лівому верхньому куті з'являється компактна напівпрозора плаваюча кнопка `▼ Bar (F10)`.
     * Виправлено та активовано повноекранний режим (`F11`, кнопку `⛶ Fullscreen` у тулбарі та HTML5-кнопку `⛶` всередині 3D-вікна веб-інтерфейсу): увімкнено прапорець `FullScreenSupportEnabled` у `QWebEngineSettings`, налаштовано обробку сигналу `fullScreenRequested` (`request.accept()`), а вихід реалізовано за клавішами `F11` або `Escape`.
     * Прибрано блок введення `Initial Spawn Pose` з інтерфейсу лаунчера для повернення до компактного вигляду.
  7. **Середовище ROS 2 при запуску лаунчера через `.desktop`:**
     * **Причина:** GNOME не виконує `~/.bashrc`, тому процеси без нього не отримували `CYCLONEDDS_URI` (`MaxAutoParticipantIndex=500`). За замовчуванням CycloneDDS дозволяє лише ~10 учасників, тож Nav2 падав (`collision_monitor`), коли запускався з `mission_manager`.
     * **Виправлення:** `smart_launcher.py` на старті завантажує повне середовище інтерактивного терміналу (`bash -ic`) і передає його всім дочірнім `tmux`-сесіям. `mission_manager.py` не змінювався (тимчасову правку відкатили).
