import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import { isAxiosError } from "axios";
import dayjs from "dayjs";
import { useMemo, useState } from "react";

import { apiClient } from "../../api/client";
import type { WearableDevice } from "./types";

type DeviceFormValues = Pick<WearableDevice, "provider" | "external_device_id" | "identifier_type" | "model">;
type DeviceFilter = "all" | "bound" | "unbound" | "disabled";

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

function isBound(device: WearableDevice) {
  return Boolean(device.current_patient_name);
}

export function DeviceInventoryPage() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm<DeviceFormValues>();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<DeviceFilter>("all");

  const devicesQuery = useQuery({
    queryKey: ["wearable-devices"],
    queryFn: async () => (await apiClient.get<WearableDevice[]>("/wearables/devices/")).data,
  });

  const createDevice = useMutation({
    mutationFn: async (values: DeviceFormValues) =>
      (
        await apiClient.post<WearableDevice>("/wearables/devices/", {
          provider: values.provider.trim(),
          external_device_id: values.external_device_id.trim(),
          identifier_type: values.identifier_type.trim(),
          model: values.model.trim(),
        })
      ).data,
    onSuccess: (device) => {
      queryClient.setQueryData<WearableDevice[]>(["wearable-devices"], (current = []) => [device, ...current]);
      form.resetFields();
      setCreateOpen(false);
    },
  });

  const statusCheck = useMutation({
    mutationFn: async (deviceId: number) =>
      (await apiClient.post(`/wearables/devices/${deviceId}/check-status/`)).data,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["wearable-devices"] }),
  });

  const dataSource = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();
    return (devicesQuery.data ?? []).filter((device) => {
      const matchesSearch =
        !normalizedSearch ||
        device.short_code.includes(normalizedSearch) ||
        device.external_device_id.toLowerCase().includes(normalizedSearch);
      if (!matchesSearch) return false;
      if (filter === "bound") return device.enabled && isBound(device);
      if (filter === "unbound") return device.enabled && !isBound(device);
      if (filter === "disabled") return !device.enabled;
      return true;
    });
  }, [devicesQuery.data, filter, search]);

  return (
    <Card
      title="设备台账"
      extra={
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          新增设备
        </Button>
      }
    >
      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          allowClear
          aria-label="搜索固定简码或厂商标识"
          placeholder="搜索固定简码或厂商标识"
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

      {devicesQuery.isError ? (
        <Alert type="error" showIcon message={errorMessage(devicesQuery.error, "设备台账加载失败")} />
      ) : (
        <Table<WearableDevice>
          rowKey="id"
          loading={devicesQuery.isLoading}
          dataSource={dataSource}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 920 }}
          locale={{ emptyText: "暂无设备，请先录入设备。" }}
          columns={[
            { title: "固定简码", dataIndex: "short_code", width: 110, render: (value: string) => <Typography.Text strong>{value}</Typography.Text> },
            { title: "型号", dataIndex: "model", width: 150, render: (value: string) => value || "—" },
            {
              title: "当前患者",
              dataIndex: "current_patient_name",
              width: 150,
              render: (value: string | null | undefined, device) =>
                !device.enabled ? <Tag>已停用</Tag> : value ? value : "未绑定",
            },
            { title: "最近通信", dataIndex: "last_communication_at", width: 170, render: formatTime },
            { title: "最近同步", dataIndex: "last_sync_at", width: 170, render: formatTime },
            {
              title: "操作",
              key: "actions",
              width: 120,
              render: (_: unknown, device) => (
                <Button
                  type="link"
                  style={{ paddingInline: 0 }}
                  disabled={!device.enabled}
                  loading={statusCheck.isPending && statusCheck.variables === device.id}
                  onClick={() => statusCheck.mutate(device.id)}
                >
                  通信测试
                </Button>
              ),
            },
          ]}
        />
      )}

      <Modal title="新增设备" open={createOpen} footer={null} destroyOnHidden onCancel={() => setCreateOpen(false)}>
        <Form form={form} layout="vertical" onFinish={(values) => createDevice.mutate(values)}>
          <Form.Item label="厂商" name="provider" rules={[{ required: true, message: "请输入厂商" }]}>
            <Input placeholder="例如 miwitracker" />
          </Form.Item>
          <Form.Item label="厂商设备标识" name="external_device_id" rules={[{ required: true, message: "请输入厂商设备标识" }]}>
            <Input placeholder="设备在厂商平台中的标识" />
          </Form.Item>
          <Form.Item label="标识类型" name="identifier_type" rules={[{ required: true, message: "请输入标识类型" }]}>
            <Input placeholder="例如 device_id、sn 或 imei" />
          </Form.Item>
          <Form.Item label="设备型号" name="model" rules={[{ required: true, message: "请输入设备型号" }]}>
            <Input placeholder="设备型号" />
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
