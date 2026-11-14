import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { vexcelApiPlugin } from './server/vexcelPlugin';
import { resolve } from 'node:path';

export default defineConfig(({ mode }) => {
  const root = process.cwd();
  const local = loadEnv(mode, root, '');
  const hackathon = loadEnv(mode, resolve(root, '../Vexcel_API_Hackathon_Tutorial_PDF_PY'), '');
  const serverEnv = { ...hackathon, ...local };
  for (const name of ['VEXCEL_API_KEY', 'NRP_API_KEY', 'LANDLENS_AGENT_API_KEY', 'LANDLENS_AGENT_BASE_URL', 'LANDLENS_AGENT_MODEL', 'LANGSMITH_API_KEY', 'LANGSMITH_ENDPOINT', 'LANGSMITH_AGENT_ID', 'LANGSMITH_AGENT_ENVIRONMENT', 'LANGSMITH_TRACING', 'LANGSMITH_PROJECT', 'PHOTON_API_KEY', 'PHOTON_PROJECT_ID', 'PHOTON_AGENT_USER_ID', 'DATABASE_URL', 'ML_MODEL_URL', 'CROPFIT_URL', 'ML_STRICT', 'ML_MODEL_TIMEOUT_MS', 'ML_MODEL_API', 'ML_SOIL_PH', 'ML_IRRIGATED']) {
    if (serverEnv[name]) process.env[name] = serverEnv[name];
  }
  if (!process.env.LANGSMITH_API_KEY && serverEnv.LANGCHAIN_API_KEY) process.env.LANGSMITH_API_KEY = serverEnv.LANGCHAIN_API_KEY;
  return { base: './', plugins: [react(), vexcelApiPlugin(root)] };
});
