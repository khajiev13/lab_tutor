import { useData } from "@/features/arcd-agent/context/DataContext";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface HeaderStudentPickerProps {
  compact?: boolean;
  showAccuracy?: boolean;
}

export function HeaderStudentPicker({ compact = false, showAccuracy = true }: HeaderStudentPickerProps = {}) {
  const { currentDataset, selectedUid, setSelectedUid } = useData();

  if (!currentDataset || currentDataset.students.length === 0) return null;

  return (
    <Select value={selectedUid} onValueChange={setSelectedUid}>
      <SelectTrigger className={`${compact ? "w-[180px]" : "w-[220px]"} text-xs h-8`}>
        <SelectValue placeholder="Select a student" />
      </SelectTrigger>
      <SelectContent>
        {currentDataset.students.map((s) => (
          <SelectItem key={s.uid} value={s.uid}>
            {showAccuracy
              ? `Student ${s.uid} — ${(s.summary.accuracy * 100).toFixed(1)}% acc`
              : `Student ${s.uid}`}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
