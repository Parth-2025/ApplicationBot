// frontend/src/components/JobDetail.tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Descriptions, Button, Space, message, Input } from "antd";
import {
  fetchJob,
  updateJobStatus,
  generateTailoredResume,
  saveTailoredResume,
} from "../api/client";
import type { Job } from "../api/client";
import MarkAppliedModal from "./MarkAppliedModal";

const { TextArea } = Input;

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = () => {
    if (!id) return;
    fetchJob(Number(id))
      .then((fetched) => {
        setJob(fetched);
        setDraft(fetched.tailored_resume_text ?? "");
      })
      .catch((err) =>
        message.error(err instanceof Error ? err.message : "Failed to load job")
      );
  };

  useEffect(load, [id]);

  if (!job) return null;

  const handleIgnore = async () => {
    try {
      await updateJobStatus(job.id, "ignored");
      message.success("Job marked ignored");
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Failed to update job");
    }
  };

  const handleReject = async () => {
    try {
      await updateJobStatus(job.id, "rejected");
      message.success("Job marked rejected");
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Failed to update job");
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const { draft: generated } = await generateTailoredResume(job.id);
      setDraft(generated);
      message.success("Draft generated - review and save below");
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "Failed to generate tailored resume"
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveTailoredResume(job.id, draft);
      message.success("Tailored resume saved");
      load();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "Failed to save tailored resume"
      );
    } finally {
      setSaving(false);
    }
  };

  // Mirrors backend ALLOWED_TRANSITIONS: new, tailored, and applied can all
  // transition to rejected.
  const canReject =
    job.status === "new" || job.status === "tailored" || job.status === "applied";
  const canTailor = job.status === "new" || job.status === "tailored";

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
        {job.status === "applied" && (
          <>
            <Descriptions.Item label="Applied Date">
              {job.applied_date ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="Application Number">
              {job.application_number ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="Notes">{job.notes ?? "—"}</Descriptions.Item>
          </>
        )}
      </Descriptions>

      {canTailor && (
        <div style={{ margin: "16px 0" }}>
          <Space style={{ marginBottom: 8 }}>
            <Button loading={generating} onClick={handleGenerate}>
              Generate Tailored Resume
            </Button>
            <Button type="primary" loading={saving} disabled={!draft} onClick={handleSave}>
              Save
            </Button>
          </Space>
          <TextArea
            rows={20}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Click Generate to draft a tailored resume, or paste/edit your own here before saving."
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
        {canReject && (
          <Button danger onClick={handleReject}>
            Reject
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
