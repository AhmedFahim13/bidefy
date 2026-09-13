export const CATEGORY_LABELS: Record<string, string> = {
  roads_bridges: "Roads and bridges",
  buildings_civil: "Buildings and civil works",
  water_sanitation: "Water and sanitation",
  electrical_power: "Electrical and power",
  it_equipment: "IT equipment and software",
  office_supplies: "Office supplies",
  furniture: "Furniture",
  medical: "Medical and pharmaceutical",
  vehicles_transport: "Vehicles and transport",
  food_catering: "Food and catering",
  textiles_uniforms: "Textiles and uniforms",
  printing_media: "Printing and media",
  security_cleaning_services: "Security and cleaning services",
  consultancy: "Consultancy",
  agriculture_environment: "Agriculture and environment",
};

export function categoryLabel(slug: string | null | undefined): string {
  if (!slug) return "";
  return CATEGORY_LABELS[slug] ?? slug.replace(/_/g, " ");
}
