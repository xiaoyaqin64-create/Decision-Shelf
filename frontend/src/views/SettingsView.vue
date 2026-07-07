<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const status = ref<any>(null)
const form = reactive({
  deepseek_api_key: '',
  deepseek_base_url: 'https://api.deepseek.com',
  deepseek_model: 'deepseek-v4-flash',
  tmdb_read_access_token: '',
  musicbrainz_contact: '',
})

async function refresh() {
  status.value = await api.settings()
  form.deepseek_base_url = status.value.deepseek_base_url
  form.deepseek_model = status.value.deepseek_model
  form.musicbrainz_contact = status.value.musicbrainz_contact
}

onMounted(async () => {
  try { await refresh() }
  catch (e: any) { error.value = e.message }
  finally { loading.value = false }
})

async function save() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    status.value = await api.updateSettings(form)
    form.deepseek_api_key = ''
    form.tmdb_read_access_token = ''
    window.dispatchEvent(new Event('decision-shelf-config-changed'))
    success.value = '设置已保存在这台电脑上，并已立即生效。'
  } catch (e: any) { error.value = e.message }
  finally { saving.value = false }
}

async function removeSecret(name: 'deepseek' | 'tmdb') {
  if (!confirm('确定要移除这项密钥吗？')) return
  try {
    status.value = await api.removeSecret(name)
    window.dispatchEvent(new Event('decision-shelf-config-changed'))
    success.value = '密钥已移除。'
  } catch (e: any) { error.value = e.message }
}
</script>

<template>
  <section class="page narrow settings-page">
    <header class="hero compact">
      <div>
        <p class="eyebrow">LOCAL SETTINGS</p>
        <h1>连接你的服务</h1>
        <p>所有密钥只保存在这台电脑，不会进入书架数据库，也不会显示在页面中。</p>
      </div>
    </header>

    <p v-if="loading">正在读取设置…</p>
    <form v-else class="paper settings-form" @submit.prevent="save">
      <section>
        <div class="settings-heading">
          <div><h2>DeepSeek</h2><p>用于理解你的状态、补全内容和自由探索。</p></div>
          <span :class="status?.deepseek_configured ? 'configured' : 'unconfigured'">
            {{ status?.deepseek_configured ? '已配置' : '未配置' }}
          </span>
        </div>
        <label>API Key
          <input v-model="form.deepseek_api_key" type="password" autocomplete="off"
            :placeholder="status?.deepseek_configured ? '已保存；留空则保持不变' : 'sk-…'">
        </label>
        <div class="settings-grid">
          <label>API 地址<input v-model="form.deepseek_base_url" type="url" required></label>
          <label>模型名称<input v-model="form.deepseek_model" required></label>
        </div>
        <button v-if="status?.deepseek_configured" type="button" class="text-button danger-text" @click="removeSecret('deepseek')">移除 DeepSeek Key</button>
      </section>

      <section>
        <div class="settings-heading">
          <div><h2>TMDb</h2><p>用于搜索电影、海报、导演和简介。</p></div>
          <span :class="status?.tmdb_configured ? 'configured' : 'unconfigured'">
            {{ status?.tmdb_configured ? '已配置' : '未配置' }}
          </span>
        </div>
        <label>Read Access Token
          <input v-model="form.tmdb_read_access_token" type="password" autocomplete="off"
            :placeholder="status?.tmdb_configured ? '已保存；留空则保持不变' : '粘贴 TMDb Read Access Token'">
        </label>
        <button v-if="status?.tmdb_configured" type="button" class="text-button danger-text" @click="removeSecret('tmdb')">移除 TMDb Token</button>
      </section>

      <section>
        <div class="settings-heading"><div><h2>MusicBrainz</h2><p>专辑搜索无需密钥，但要求填写联系邮箱或个人网址。</p></div></div>
        <label>联系信息<input v-model="form.musicbrainz_contact" placeholder="name@example.com"></label>
      </section>

      <p v-if="error" class="error-box">{{ error }}</p>
      <p v-if="success" class="success-box">{{ success }}</p>
      <button class="settings-save" :disabled="saving">{{ saving ? '保存中…' : '保存设置' }}</button>
    </form>
  </section>
</template>
