import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import AgriculturePage from './pages/AgriculturePage';
import OnboardingPage from './pages/OnboardingPage';
import PlanPage from './pages/PlanPage';
import ModelPage from './pages/ModelPage';
import SensorsPage from './pages/SensorsPage';

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/start" element={<OnboardingPage />} />
        <Route path="/plan" element={<PlanPage />} />
        <Route path="/model" element={<ModelPage />} />
        <Route path="/sensors" element={<SensorsPage />} />
        <Route path="/agriculture/:mode" element={<AgriculturePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}
