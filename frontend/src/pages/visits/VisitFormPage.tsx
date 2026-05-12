import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  InputNumber,
  Radio,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";

type Assessments = {
  sppb?: {
    balance?: number | null;
    gait?: number | null;
    chair_stand?: number | null;
    total?: number | null;
  };
  moca?: { total?: number | null };
  tug_seconds?: number | null;
  grip_strength_kg?: number | null;
  frailty?: "robust" | "pre_frail" | "frail" | null;
};

type VisitDetail = {
  id: number;
  project_patient: number;
  visit_type: "T0" | "T1" | "T2";
  status: "draft" | "completed";
  visit_date: string | null;
  form_data: {
    assessments: Assessments;
    computed_assessments: Assessments;
  };
};

type FormState = {
  sppb_balance: number | null;
  sppb_gait: number | null;
  sppb_chair_stand: number | null;
  sppb_total: number | null;
  moca_total: number | null;
  tug_seconds: number | null;
  grip_strength_kg: number | null;
  frailty: "robust" | "pre_frail" | "frail" | null;
};

const EMPTY_FORM: FormState = {
  sppb_balance: null,
  sppb_gait: null,
  sppb_chair_stand: null,
  sppb_total: null,
  moca_total: null,
  tug_seconds: null,
  grip_strength_kg: null,
  frailty: null,
};

function pickInitial(
  manual: number | null | undefined,
  computed: number | null | undefined,
): { value: number | null; fromComputed: boolean } {
  if (manual !== undefined && manual !== null) {
    return { value: manual, fromComputed: false };
  }
  if (computed !== undefined && computed !== null) {
    return { value: computed, fromComputed: true };
  }
  return { value: null, fromComputed: false };
}

function pickInitialEnum(
  manual: FormState["frailty"] | undefined,
  computed: FormState["frailty"] | undefined,
): { value: FormState["frailty"]; fromComputed: boolean } {
  if (manual) return { value: manual, fromComputed: false };
  if (computed) return { value: computed, fromComputed: true };
  return { value: null, fromComputed: false };
}

function buildInitialForm(visit: VisitDetail): {
  state: FormState;
  computedFlags: Record<keyof FormState, boolean>;
} {
  const m = visit.form_data.assessments ?? {};
  const c = visit.form_data.computed_assessments ?? {};
  const flags = {} as Record<keyof FormState, boolean>;
  const state: FormState = { ...EMPTY_FORM };

  const num = (
    key: keyof FormState,
    manual?: number | null,
    computed?: number | null,
  ) => {
    const r = pickInitial(manual ?? null, computed ?? null);
    state[key] = r.value as never;
    flags[key] = r.fromComputed;
  };

  num("sppb_balance", m.sppb?.balance, c.sppb?.balance);
  num("sppb_gait", m.sppb?.gait, c.sppb?.gait);
  num("sppb_chair_stand", m.sppb?.chair_stand, c.sppb?.chair_stand);
  num("sppb_total", m.sppb?.total, c.sppb?.total);
  num("moca_total", m.moca?.total, c.moca?.total);
  num("tug_seconds", m.tug_seconds, c.tug_seconds);
  num("grip_strength_kg", m.grip_strength_kg, c.grip_strength_kg);

  const f = pickInitialEnum(m.frailty ?? null, c.frailty ?? null);
  state.frailty = f.value;
  flags.frailty = f.fromComputed;

  return { state, computedFlags: flags };
}

function diffPatch(
  initial: FormState,
  current: FormState,
): { form_data?: { assessments: Assessments } } {
  const changed: Assessments = {};
  let hasChange = false;

  const setSppb = (
    key: "balance" | "gait" | "chair_stand" | "total",
    v: number | null,
  ) => {
    changed.sppb = { ...(changed.sppb ?? {}), [key]: v };
    hasChange = true;
  };

  if (initial.sppb_balance !== current.sppb_balance)
    setSppb("balance", current.sppb_balance);
  if (initial.sppb_gait !== current.sppb_gait)
    setSppb("gait", current.sppb_gait);
  if (initial.sppb_chair_stand !== current.sppb_chair_stand)
    setSppb("chair_stand", current.sppb_chair_stand);
  if (initial.sppb_total !== current.sppb_total)
    setSppb("total", current.sppb_total);

  if (initial.moca_total !== current.moca_total) {
    changed.moca = { total: current.moca_total };
    hasChange = true;
  }
  if (initial.tug_seconds !== current.tug_seconds) {
    changed.tug_seconds = current.tug_seconds;
    hasChange = true;
  }
  if (initial.grip_strength_kg !== current.grip_strength_kg) {
    changed.grip_strength_kg = current.grip_strength_kg;
    hasChange = true;
  }
  if (initial.frailty !== current.frailty) {
    changed.frailty = current.frailty;
    hasChange = true;
  }

  return hasChange ? { form_data: { assessments: changed } } : {};
}

const computedHint = <Tag color="blue">系统预填值</Tag>;

export function VisitFormPage() {
  const { visitId } = useParams<{ visitId: string }>();
  const id = Number(visitId);
  const qc = useQueryClient();
  const [initial, setInitial] = useState<FormState>(EMPTY_FORM);
  const [current, setCurrent] = useState<FormState>(EMPTY_FORM);
  const [computedFlags, setComputedFlags] = useState<
    Record<keyof FormState, boolean>
  >({} as Record<keyof FormState, boolean>);

  const { data: visit, isLoading } = useQuery({
    queryKey: ["visit", id],
    queryFn: async () => {
      const r = await apiClient.get<VisitDetail>(`/visits/${id}/`);
      return r.data;
    },
    enabled: !!id,
  });

  useEffect(() => {
    if (!visit) return;
    const { state, computedFlags: flags } = buildInitialForm(visit);
    setInitial(state);
    setCurrent(state);
    setComputedFlags(flags);
  }, [visit]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = diffPatch(initial, current);
      if (!body.form_data) return null;
      const r = await apiClient.patch(`/visits/${id}/`, body);
      return r.data;
    },
    onSuccess: async (data) => {
      if (data) {
        message.success("已保存");
        await qc.invalidateQueries({ queryKey: ["visit", id] });
      } else {
        message.info("没有改动");
      }
    },
    onError: () => message.error("保存失败"),
  });

  const completeMutation = useMutation({
    mutationFn: async () => {
      const r = await apiClient.patch(`/visits/${id}/`, { status: "completed" });
      return r.data;
    },
    onSuccess: async () => {
      message.success("已标记完成");
      await qc.invalidateQueries({ queryKey: ["visit", id] });
    },
    onError: () => message.error("操作失败"),
  });

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setCurrent((prev) => ({ ...prev, [key]: value }));
    setComputedFlags((prev) => ({ ...prev, [key]: false }));
  };

  const renderHint = (key: keyof FormState) =>
    computedFlags[key] ? computedHint : null;

  const headerExtra = useMemo(() => {
    if (!visit) return null;
    return (
      <Space>
        <Tag color="geekblue">{visit.visit_type}</Tag>
        <Tag color={visit.status === "completed" ? "green" : "default"}>
          {visit.status === "completed" ? "已完成" : "草稿"}
        </Tag>
      </Space>
    );
  }, [visit]);

  return (
    <Card title="访视表单" loading={isLoading} extra={headerExtra}>
      {visit && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="访视类型">{visit.visit_type}</Descriptions.Item>
            <Descriptions.Item label="访视日期">
              {visit.visit_date ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {visit.status === "completed" ? "已完成" : "草稿"}
            </Descriptions.Item>
          </Descriptions>

          {Object.values(computedFlags).some(Boolean) && (
            <Alert
              type="info"
              showIcon
              message="部分字段使用了“系统预填值”，确认或修改后保存即写入医生填写值。"
            />
          )}

          <Form layout="vertical">
            <Card type="inner" title="SPPB" style={{ marginBottom: 12 }}>
              <Space wrap size="middle" align="end">
                <Form.Item label="平衡">
                  <InputNumber
                    aria-label="SPPB 平衡"
                    value={current.sppb_balance ?? undefined}
                    onChange={(v) => set("sppb_balance", (v as number) ?? null)}
                  />
                  {renderHint("sppb_balance")}
                </Form.Item>
                <Form.Item label="步行">
                  <InputNumber
                    aria-label="SPPB 步行"
                    value={current.sppb_gait ?? undefined}
                    onChange={(v) => set("sppb_gait", (v as number) ?? null)}
                  />
                  {renderHint("sppb_gait")}
                </Form.Item>
                <Form.Item label="坐立">
                  <InputNumber
                    aria-label="SPPB 坐立"
                    value={current.sppb_chair_stand ?? undefined}
                    onChange={(v) =>
                      set("sppb_chair_stand", (v as number) ?? null)
                    }
                  />
                  {renderHint("sppb_chair_stand")}
                </Form.Item>
                <Form.Item label="SPPB 总分">
                  <InputNumber
                    aria-label="SPPB 总分"
                    value={current.sppb_total ?? undefined}
                    onChange={(v) => set("sppb_total", (v as number) ?? null)}
                  />
                  {renderHint("sppb_total")}
                </Form.Item>
              </Space>
            </Card>

            <Card type="inner" title="MoCA" style={{ marginBottom: 12 }}>
              <Form.Item label="MoCA 总分">
                <InputNumber
                  aria-label="MoCA 总分"
                  value={current.moca_total ?? undefined}
                  onChange={(v) => set("moca_total", (v as number) ?? null)}
                />
                {renderHint("moca_total")}
              </Form.Item>
            </Card>

            <Card type="inner" title="其他评估" style={{ marginBottom: 12 }}>
              <Space wrap size="middle" align="end">
                <Form.Item label="TUG（秒）">
                  <InputNumber
                    aria-label="TUG"
                    value={current.tug_seconds ?? undefined}
                    onChange={(v) => set("tug_seconds", (v as number) ?? null)}
                  />
                  {renderHint("tug_seconds")}
                </Form.Item>
                <Form.Item label="握力（kg）">
                  <InputNumber
                    aria-label="握力"
                    value={current.grip_strength_kg ?? undefined}
                    onChange={(v) =>
                      set("grip_strength_kg", (v as number) ?? null)
                    }
                  />
                  {renderHint("grip_strength_kg")}
                </Form.Item>
                <Form.Item label="衰弱判定">
                  <Radio.Group
                    value={current.frailty ?? undefined}
                    onChange={(e) =>
                      set("frailty", e.target.value as FormState["frailty"])
                    }
                  >
                    <Radio value="robust">非衰弱</Radio>
                    <Radio value="pre_frail">衰弱前期</Radio>
                    <Radio value="frail">衰弱</Radio>
                  </Radio.Group>
                  {renderHint("frailty")}
                </Form.Item>
              </Space>
            </Card>

            <Space>
              <Button
                type="primary"
                aria-label="保存"
                loading={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                保存
              </Button>
              <Button
                aria-label="标记已完成"
                loading={completeMutation.isPending}
                disabled={visit.status === "completed"}
                onClick={() => completeMutation.mutate()}
              >
                标记已完成
              </Button>
              <Typography.Text type="secondary">
                保存只会发送改动字段；状态切换走独立 PATCH。
              </Typography.Text>
            </Space>
          </Form>
        </Space>
      )}
    </Card>
  );
}

