import { Alert, Button, List, Modal, Typography } from "antd";

export type DestructiveActionModalProps = {
  open: boolean;
  title: string;
  okText?: string;
  impactSummary: string[];
  /** 有值时禁止确认，仅展示阻断说明 */
  blockedReason?: string | null;
  confirmLoading?: boolean;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
};

export function DestructiveActionModal({
  open,
  title,
  okText = "确认",
  impactSummary,
  blockedReason,
  confirmLoading,
  onCancel,
  onConfirm,
}: DestructiveActionModalProps) {
  const blocked = Boolean(blockedReason);
  return (
    <Modal
      open={open}
      title={title}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="ok"
          danger
          type="primary"
          loading={confirmLoading}
          disabled={blocked}
          onClick={() => void onConfirm()}
        >
          {okText}
        </Button>,
      ]}
      destroyOnClose
      width={520}
    >
      {blocked && blockedReason ? (
        <Alert type="warning" showIcon message="当前无法执行该操作" description={blockedReason} />
      ) : (
        <>
          <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
            请确认以下影响后再继续：
          </Typography.Paragraph>
          <List
            size="small"
            dataSource={impactSummary}
            renderItem={(item) => (
              <List.Item style={{ paddingLeft: 0, border: "none" }}>
                <Typography.Text>· {item}</Typography.Text>
              </List.Item>
            )}
          />
        </>
      )}
    </Modal>
  );
}
