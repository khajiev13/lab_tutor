export interface MarketDemandCountry {
  label: string;
  value: string;
}

export const DEFAULT_MARKET_DEMAND_COUNTRY = "USA";

export const MARKET_DEMAND_COUNTRIES: MarketDemandCountry[] = [
  { label: "United States", value: "USA" },
  { label: "China", value: "China" },
  { label: "United Kingdom", value: "UK" },
  { label: "Canada", value: "Canada" },
  { label: "Australia", value: "Australia" },
  { label: "Singapore", value: "Singapore" },
];

export function getMarketDemandCountryLabel(value: string | null | undefined): string {
  return (
    MARKET_DEMAND_COUNTRIES.find((country) => country.value === value)?.label ??
    "United States"
  );
}
