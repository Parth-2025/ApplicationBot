// frontend/src/components/JobDetail.tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Descriptions, Button, Space, message } from "antd";
import { fetchJob, updateJobStatus, Job } from "../api/client";
import MarkAppliedModal from "./MarkAppliedModal";

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const load = () => {
    if (!id) return;
    fetchJob(Number(id))
      .then(setJob)
      .catch(() => message.error("Failed to load job"));
  };

  useEffect(load, [id]);

  if (!job) return null;

  const handleIgnore = async () => {
    try {
      await updateJobStatus(job.id, "ignored");
      message.success("Job marked ignored");
      load();
    } catch {
      message.error("Failed to update job");
    }
  };

  return (
    <div>
      <Descriptions title={`${job.company} — ${job.role_title}`} bordered column={1}>
        <Descriptions.Item label="Status">{job.status}</Descriptions.Item>
        <Descriptions.Item label="Eligibility">{job.eligibility}</Descriptions.Item>
        <Descriptions.Item label="Location">{job.location ?? "—"}</Descriptions.Item>
        <Descriptions.Item label="Source">
          <a href={job.source_url} target="_blank" rel="noreferrer">
            {job.source}
          </a>
        </Descriptions.Item>
        <Descriptions.Item label="Job Description">
          {job.raw_job_description ?? "—"}
        </Descriptions.Item>
      </Descriptions>

      {job.status === "tailored" && (
        <div style={{ margin: "16px 0" }}>
          <iframe
            title="tailored-resume"
            src={`http://localhost:8000/jobs/${job.id}/resume`}
            width="100%"
            height="600px"
          />
        </div>
      )}

      <Space style={{ marginTop: 16 }}>
        {job.status === "tailored" && (
          <Button type="primary" onClick={() => setModalOpen(true)}>
            Mark Applied
          </Button>
        )}
        {(job.status === "new" || job.status === "tailored") && (
          <Button danger onClick={handleIgnore}>
            Ignore
          </Button>
        )}
      </Space>

      <MarkAppliedModal
        jobId={job.id}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={() => {
          setModalOpen(false);
          load();
        }}
      />
    </div>
  );
}
