import { useData } from "@/features/arcd-agent/context/DataContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function DatasetSwitcher() {
  const { portfolioData, activeDatasetId, setActiveDatasetId } = useData();

  if (!portfolioData || portfolioData.datasets.length <= 1) return null;

  return (
    <Tabs value={activeDatasetId} onValueChange={setActiveDatasetId}>
      <TabsList>
        {portfolioData.datasets.map((ds) => (
          <TabsTrigger key={ds.id} value={ds.id} className="text-xs">
            {ds.name}
            <span className="ml-1.5 text-[10px] opacity-60">
              AUC {ds.model_info.best_val_auc.toFixed(2)}
            </span>
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
