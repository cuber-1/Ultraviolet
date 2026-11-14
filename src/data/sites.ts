export type Market = 'Houston' | 'Los Angeles';

export type Site = {
  id: string;
  address: string;
  city: Market;
  state: 'TX' | 'CA';
  acres: number;
  listing: string;
  use: string;
  lat: number;
  lon: number;
  parcel: string;
  headline: string;
  summary: string;
};

export type ImageryView = {
  id: string;
  label: string;
  description: string;
  filename: string;
};

export const IMAGERY_VIEWS: ImageryView[] = [
  { id: 'ortho', label: 'Ortho', description: 'Straight-down parcel view', filename: 'ortho_parcel.jpg' },
  { id: 'north', label: 'North', description: 'North-facing oblique', filename: 'oblique-north.jpg' },
  { id: 'east', label: 'East', description: 'East-facing oblique', filename: 'oblique-east.jpg' },
  { id: 'south', label: 'South', description: 'South-facing oblique', filename: 'oblique-south.jpg' },
  { id: 'west', label: 'West', description: 'West-facing oblique', filename: 'oblique-west.jpg' },
];

export const SITES: Site[] = [
  {
    id: '10170185', address: '13909 Mandolin Dr', city: 'Houston', state: 'TX', acres: 1.37,
    listing: 'Auction · vacant infill lot', use: 'Vacant urban land', lat: 29.9778405, lon: -95.5695495,
    parcel: '1396470010003', headline: 'NW Houston infill development opportunity',
    summary: 'A wooded infill parcel positioned between established residential and commercial uses in northwest Houston.',
  },
  {
    id: '12220273', address: 'Willow Chase Blvd & Centerfield Dr', city: 'Houston', state: 'TX', acres: 2.69,
    listing: 'Auction · corner development site', use: 'Commercial pad site', lat: 29.9655475, lon: -95.5480185,
    parcel: '1207520010001', headline: 'High-visibility Willowbrook corner pad site',
    summary: 'A prominent corner parcel with broad street exposure and proximity to retail, hospitality, and multifamily properties.',
  },
  {
    id: '21276388', address: '8521 Horner St', city: 'Los Angeles', state: 'CA', acres: 0.22,
    listing: 'For sale · proposed 35-unit development', use: 'High-density housing', lat: 34.0503123, lon: -118.377005,
    parcel: '4303-032-022', headline: 'Five-story 35-unit RTI development site',
    summary: 'A compact Los Angeles infill parcel positioned for a proposed multifamily development near established neighborhood services.',
  },
  {
    id: '21290728', address: '7210 S Western Ave', city: 'Los Angeles', state: 'CA', acres: 0.3,
    listing: 'For sale · retail or multifamily development', use: 'Mixed-use development', lat: 33.9740596, lon: -118.3086724,
    parcel: '6018-001-002 / 003 / 004 / 024', headline: 'Entitled retail or multifamily development',
    summary: 'Four assembled parcels on South Western Avenue with commercial, residential, and mixed-use development potential.',
  },
];

export function imagePath(siteId: string, filename: string) {
  return `${import.meta.env.BASE_URL}vexcel/${siteId}/${filename}`;
}
