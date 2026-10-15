import { Link } from "react-router-dom";

export function MaterialsReadinessNotice({ courseId, message, showLink = true }: {
  courseId: number;
  message: string;
  showLink?: boolean;
}) {
  return <p role="status" className="text-sm text-muted-foreground">
    <span>{message}</span>{showLink && <> <Link className="underline underline-offset-4" to={`/courses/${courseId}/architect?step=materials`}>Course materials</Link></>}
  </p>;
}
