// frontend/src/components/JobTable.tsx
import { useEffect, useState } from "react";
import { Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { fetchJobs } from "../api/client";
import type { Job } from "../api/client";

const statusColors: Record<Job["status"], string> = {
  new: "blue",
  tailored: "gold",
  applied: "green",
  rejected: "red",
  ignored: "default",
};

export default function JobTable() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJobs()
      .then(setJobs)
      .catch((err) =>
        message.error(err instanceof Error ? err.message : "Failed to load jobs")
      )
      .finally(() => setLoading(false));
  }, []);

  const columns: ColumnsType<Job> = [
    {
      title: "Company",
      dataIndex: "company",
      sorter: (a, b) => a.company.localeCompare(b.company),
    },
    { title: "Role", dataIndex: "role_title" },
    {
      title: "Status",
      dataIndex: "status",
      filters: Object.keys(statusColors).map((s) => ({ text: s, value: s })),
      onFilter: (value, record) => record.status === value,
      render: (status: Job["status"]) => (
        <Tag color={statusColors[status]}>{status}</Tag>
      ),
    },
    { title: "Eligibility", dataIndex: "eligibility" },
    {
      title: "Discovered",
      dataIndex: "discovered_date",
      sorter: (a, b) => a.discovered_date.localeCompare(b.discovered_date),
    },
    {
      title: "",
      key: "actions",
      render: (_, record) => <Link to={`/jobs/${record.id}`}>View</Link>,
    },
  ];

  return <Table rowKey="id" loading={loading} columns={columns} dataSource={jobs} />;
}
