import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Descriptions } from "antd";
import { isAxiosError } from "axios";
import { useParams } from "react-router-dom";

import { apiClient } from "../../api/client";

type Patient = {
  id: number;
  name: string;
  phone: string;
  gender?: string | null;
  age?: number | null;
  primary_doctor?: number | null;
  symptom_note?: string | null;
  is_active?: boolean;
};

function displayValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

export function PatientDetailPage() {
  const { patientId } = useParams();
  const id = Number(patientId);

  const { data: patient, isLoading, isError, error } = useQuery({
    queryKey: ["patient", patientId ?? ""],
    queryFn: async () => {
      const r = await apiClient.get<Patient>(`/patients/${id}/`);
      return r.data;
    },
    enabled: Number.isFinite(id),
  });

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的患者 ID" />;
  }

  if (isError) {
    const backendDetail =
      isAxiosError(error) && typeof (error.response?.data as any)?.detail === "string"
        ? ((error.response?.data as any).detail as string)
        : null;

    return <Alert type="error" message={backendDetail ?? "患者不存在或无权限访问"} />;
  }

  return (
    <Card loading={isLoading} title={patient ? patient.name : "患者详情"}>
      {patient && (
        <Descriptions
          bordered
          column={1}
          size="small"
          items={[
            { key: "name", label: "姓名", children: displayValue(patient.name) },
            { key: "phone", label: "手机号", children: displayValue(patient.phone) },
            { key: "gender", label: "性别", children: displayValue(patient.gender) },
            { key: "age", label: "年龄", children: displayValue(patient.age) },
            { key: "primary_doctor", label: "主治医生 ID", children: displayValue(patient.primary_doctor) },
            { key: "symptom_note", label: "备注", children: displayValue(patient.symptom_note) },
            {
              key: "is_active",
              label: "是否启用",
              children: patient.is_active === undefined ? "—" : patient.is_active ? "是" : "否",
            },
          ]}
        />
      )}
    </Card>
  );
}

