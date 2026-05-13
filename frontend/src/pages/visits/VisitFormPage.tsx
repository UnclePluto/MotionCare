import { Alert } from "antd";
import { useParams } from "react-router-dom";

import { VisitFormContent } from "./VisitFormContent";

export function VisitFormPage() {
  const { visitId } = useParams<{ visitId: string }>();
  const id = Number(visitId);

  if (!Number.isFinite(id)) {
    return <Alert type="error" message="无效的访视 ID" />;
  }

  return <VisitFormContent visitId={id} />;
}
