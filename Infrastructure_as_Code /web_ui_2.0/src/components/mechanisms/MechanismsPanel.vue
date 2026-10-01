<template>
  <div class="block-container">
    <h3 class="block-title">Block 3: Mechanisms</h3>
    <div class="grid">
      <button class="cmd-btn c-orange" @click="setLight(true)">Turn Light ON <span>LED Matrix</span></button>
      <button class="cmd-btn c-gray" @click="setLight(false)">Turn Light OFF <span>LED Matrix</span></button>
    </div>
  </div>
</template>

<script setup>
import { pubBool } from '../../services/rosConnection'

const setLight = (state) => {
  pubBool(state)
}
</script>

<style scoped>
/* Inherits global styles from style.css */
</style>
