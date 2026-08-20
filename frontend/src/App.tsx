// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider } from "antd";

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <div style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<div>Job list coming in Task 5</div>} />
          </Routes>
        </div>
      </BrowserRouter>
    </ConfigProvider>
  );
}
