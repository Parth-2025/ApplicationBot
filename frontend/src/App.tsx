// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider } from "antd";
import JobTable from "./components/JobTable";
import JobDetail from "./components/JobDetail";

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <div style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<JobTable />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
          </Routes>
        </div>
      </BrowserRouter>
    </ConfigProvider>
  );
}
