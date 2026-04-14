import { useData } from "@/features/arcd-agent/context/DataContext";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function HeaderStudentPicker() {
  const { currentDataset, selectedUid, setSelectedUid } = useData();

  if (!currentDataset || currentDataset.students.length === 0) return null;

  return (
    <Select value={selectedUid} onValueChange={setSelectedUid}>
      <SelectTrigger className="w-[220px] text-xs h-8">
        <SelectValue placeholder="Select a student" />
      </SelectTrigger>
      <SelectContent>
        {currentDataset.students.map((s) => (
          <SelectItem key={s.uid} value={s.uid}>
            Student {s.uid} — {(s.summary.accuracy * 100).toFixed(1)}% acc
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
