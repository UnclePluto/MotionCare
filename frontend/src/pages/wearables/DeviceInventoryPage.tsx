import { BellOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import { isAxiosError } from "axios";
import dayjs from "dayjs";
import { useMemo, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { WearableCommandResponse, WearableDevice, WearableStatus } from "./types";

type DeviceFormValues = { imei: string };
type DeviceFilter = "all" | "bound" | "unbound" | "disabled";
type StatusRequest = {
  deviceId: number;
  shortCode: string;
  generation: number;
};
type StatusFeedback = StatusRequest & {
  result: WearableStatus | null;
  error: unknown | null;
};
type RingFeedback = {
  type: "success" | "error";
  message: string;
};

function formatTime(value: string | null | undefined) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";
}

function errorMessage(error: unknown, fallback: string) {
  if (isAxiosError(error) && typeof error.response?.data === "object" && error.response.data) {
    const detail = (error.response.data as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function ringResultFeedback(result: WearableCommandResponse): RingFeedback {
  if (result.status === "succeeded" || result.status === "queued") {
    return { type: "success", message: "响铃指令已下发" };
  }
  return {
    type: "error",
    message: {
      offline: "设备离线，响铃未执行",
      timeout: "响铃请求超时，请稍后重试",
      failed: "设备响铃失败",
    }[result.status],
  };
}

export function DeviceInventoryPage() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<DeviceFormValues>();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<DeviceFilter>("all");
  const statusRequestGeneration = useRef(0);
  const [statusFeedback, setStatusFeedback] = useState<StatusFeedback | null>(null);
  const [ringFeedback, setRingFeedback] = useState<RingFeedback | null>(null);

  const devicesQuery = useQuery({
    queryKey: ["wearable-devices"],
    queryFn: async () => (await apiClient.get<WearableDevice[]>("/wearables/devices/")).data,
  });

  const createDevice = useMutation({
    mutationFn: async (values: DeviceFormValues) =>
      (
        await apiClient.post<WearableDevice>("/wearables/devices/", {
          imei: values.imei.trim(),
        })
      ).data,
    onSuccess: (device) => {
      queryClient.setQueryData<WearableDevice[]>(["wearable-devices"], (current = []) => [device, ...current]);
      form.resetFields();
      setCreateOpen(false);
    },
  });

  const statusCheck = useMutation({
    mutationFn: async ({ deviceId }: StatusRequest) =>
      (await apiClient.post<WearableStatus>(`/wearables/devices/${deviceId}/check-status/`)).data,
    onSuccess: (result, variables) => {
      if (
        statusRequestGeneration.current === variables.generation &&
        result.device_id === variables.deviceId
      ) {
        setStatusFeedback({ ...variables, result, error: null });
      }
      void queryClient.invalidateQueries({ queryKey: ["wearable-devices"] });
    },
    onError: (error, variables) => {
      if (statusRequestGeneration.current !== variables.generation) return;
      setStatusFeedback({ ...variables, result: null, error });
    },
  });

  const ring = useMutation({
    mutationFn: async ({ deviceId }: { deviceId: number }) =>
      (await apiClient.post<WearableCommandResponse>(`/wearables/devices/${deviceId}/ring/`)).data,
    onSuccess: (result) => setRingFeedback(ringResultFeedback(result)),
    onError: (error) => {
      setRingFeedback({ type: "error", message: errorMessage(error, "设备响铃失败") });
    },
  });

  const runStatusCheck = (device: WearableDevice) => {
    const generation = statusRequestGeneration.current + 1;
    statusRequestGeneration.current = generation;
    setStatusFeedback(null);
    statusCheck.mutate({
      deviceId: device.id,
      shortCode: device.short_code,
      generation,
    });
  };

  const dataSource = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return (devicesQuery.data ?? []).filter((device) => {
      const matchesSearch =
        !normalizedSearch ||
        device.short_code.includes(normalizedSearch) ||
        device.external_device_id.toLowerCase().includes(normalizedSearch);
      if (!matchesSearch) return false;
      if (filter === "bound") return device.enabled && device.is_bound;
      if (filter === "unbound") return device.enabled && !device.is_bound;
      if (filter === "disabled") return !device.enabled;
      return true;
    });
  }, [devicesQuery.data, filter, search]);

  const statusResult = statusFeedback?.result ?? null;
  const statusError = statusFeedback?.error ?? null;

  return (
    <Card
      title="设备管理"
      extra={
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          新增设备
        </Button>
      }
    >
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          allowClear
          aria-label="搜索固定简码或 IMEI"
          placeholder="搜索固定简码或 IMEI"
          style={{ width: 260 }}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Select<DeviceFilter>
          aria-label="设备绑定状态"
          value={filter}
          style={{ width: 150 }}
          onChange={setFilter}
          options={[
            { value: "all", label: "全部设备" },
            { value: "bound", label: "已绑定" },
            { value: "unbound", label: "未绑定" },
            { value: "disabled", label: "停用" },
          ]}
        />
      </Space>

      {statusResult ? (
        <Alert
          type={statusResult.online ? "success" : "warning"}
          showIcon
          message={`设备 ${statusFeedback?.shortCode} ${statusResult.online ? "通信正常" : "通信异常"}`}
          description={`最近通信：${formatTime(statusResult.last_communication_at)}；电量：${statusResult.battery_level ?? "—"}%`}
          style={{ marginBottom: 16 }}
        />
      ) : null}
      {statusError ? (
        <Alert
          type="warning"
          showIcon
          message={`设备 ${statusFeedback?.shortCode} 通信测试失败`}
          description={errorMessage(statusError, "设备通信测试失败")}
          style={{ marginBottom: 16 }}
        />
      ) : null}
      {ringFeedback ? (
        <Alert
          type={ringFeedback.type}
          showIcon
          closable
          message={ringFeedback.message}
          onClose={() => setRingFeedback(null)}
          style={{ marginBottom: 16 }}
        />
      ) : null}

      {devicesQuery.isError ? (
        <Alert type="error" showIcon message="设备管理加载失败" />
      ) : (
        <Table<WearableDevice>
          rowKey="id"
          loading={devicesQuery.isLoading}
          dataSource={dataSource}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 980 }}
          locale={{ emptyText: "暂无设备，请先录入设备。" }}
          columns={[
            { title: "固定简码", dataIndex: "short_code", width: 110, render: (value: string) => <Typography.Text strong>{value}</Typography.Text> },
            {
              title: "IMEI",
              dataIndex: "external_device_id",
              width: 180,
              render: (value: string, device) => device.identifier_type === "imei" ? value : "—",
            },
            { title: "型号", dataIndex: "model", width: 150, render: (value: string) => value || "—" },
            {
              title: "当前患者",
              dataIndex: "current_patient_name",
              width: 150,
              render: (value: string | null | undefined, device) =>
                !device.enabled ? (
                  <Tag>已停用</Tag>
                ) : value ? (
                  value
                ) : device.is_bound ? (
                  "已绑定（无访问权限）"
                ) : (
                  "未绑定"
                ),
            },
            { title: "最近通信", dataIndex: "last_communication_at", width: 170, render: formatTime },
            { title: "最近同步", dataIndex: "last_sync_at", width: 170, render: formatTime },
            {
              title: "操作",
              key: "actions",
              width: 180,
              render: (_: unknown, device) => (
                <Space size={8}>
                  <Button
                    type="link"
                    style={{ paddingInline: 0 }}
                    disabled={!device.enabled}
                    loading={
                      statusCheck.isPending &&
                      statusCheck.variables?.deviceId === device.id &&
                      statusCheck.variables.generation === statusRequestGeneration.current
                    }
                    onClick={() => runStatusCheck(device)}
                  >
                    通信测试
                  </Button>
                  {device.provider === "miwitracker" ? (
                    <Button
                      type="link"
                      aria-label="响铃"
                      icon={<BellOutlined />}
                      style={{ paddingInline: 0 }}
                      loading={ring.isPending && ring.variables?.deviceId === device.id}
                      onClick={() => ring.mutate({ deviceId: device.id })}
                    >
                      响铃
                    </Button>
                  ) : null}
                </Space>
              ),
            },
          ]}
        />
      )}

      <Modal title="新增设备" open={createOpen} footer={null} destroyOnHidden onCancel={() => setCreateOpen(false)}>
        <Form form={form} layout="vertical" onFinish={(values) => createDevice.mutate(values)}>
          <Form.Item
            label="IMEI"
            name="imei"
            rules={[
              { required: true, message: "请输入 IMEI" },
              {
                transform: (value: string) => value.trim(),
                pattern: /^\d{15}$/,
                message: "IMEI 必须是 15 位数字",
              },
            ]}
          >
            <Input inputMode="numeric" placeholder="请输入设备的 15 位 IMEI" />
          </Form.Item>
          {createDevice.isError ? <Alert type="error" showIcon message={errorMessage(createDevice.error, "设备录入失败")} style={{ marginBottom: 16 }} /> : null}
          <Space>
            <Button type="primary" htmlType="submit" loading={createDevice.isPending}>
              录入设备
            </Button>
            <Button onClick={() => setCreateOpen(false)}>取消</Button>
          </Space>
        </Form>
      </Modal>
    </Card>
  );
}
