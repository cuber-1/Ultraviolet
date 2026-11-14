import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import AgriculturePage from './pages/AgriculturePage';
import OnboardingPage from './pages/OnboardingPage';
import PlanPage from './pages/PlanPage';

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/start" element={<OnboardingPage />} />
        <Route path="/plan" element={<PlanPage />} />
        <Route path="/agriculture/:mode" element={<AgriculturePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}
