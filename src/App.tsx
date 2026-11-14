import { HashRouter, Route, Routes } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import ListingsPage from './pages/ListingsPage';
import ListingDetailPage from './pages/ListingDetailPage';
import MapPage from './pages/MapPage';
import AgriculturePage from './pages/AgriculturePage';

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/listings" element={<ListingsPage />} />
        <Route path="/listings/:siteId" element={<ListingDetailPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/agriculture/:mode" element={<AgriculturePage />} />
      </Routes>
    </HashRouter>
  );
}
