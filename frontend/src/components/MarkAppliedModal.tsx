// frontend/src/components/MarkAppliedModal.tsx
import { Modal, Form, DatePicker, Input, message } from "antd";
import dayjs from "dayjs";
import { markApplied } from "../api/client";

interface Props {
  jobId: number;
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function MarkAppliedModal({ jobId, open, onClose, onSuccess }: Props) {
  const [form] = Form.useForm();

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      await markApplied(jobId, {
        status: "applied",
        applied_date: values.applied_date.format("YYYY-MM-DD"),
        application_number: values.application_number,
        notes: values.notes,
      });
      message.success("Marked as applied");
      form.resetFields();
      onSuccess();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  return (
    <Modal title="Mark Applied" open={open} onOk={handleOk} onCancel={onClose}>
      <Form form={form} layout="vertical" initialValues={{ applied_date: dayjs() }}>
        <Form.Item name="applied_date" label="Applied Date" rules={[{ required: true }]}>
          <DatePicker style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="application_number" label="Application Number">
          <Input />
        </Form.Item>
        <Form.Item name="notes" label="Notes">
          <Input.TextArea rows={3} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
