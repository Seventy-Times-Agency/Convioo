/** Minimal slice of the prototype's MOCK_LEADS used by the landing preview.
 *  Reference data lives in frontend/.prototype-reference/data.jsx. */

export type LeadTemp = "hot" | "warm" | "cold";

export interface PreviewLead {
  id: string;
  name: string;
  address: string;
  rating: number;
  score: number;
  temp: LeadTemp;
}

export const PREVIEW_LEADS: PreviewLead[] = [
  {
    id: "l-1",
    name: "Northstar Roofing Co.",
    address: "1438 3rd Ave, New York, NY",
    rating: 4.7,
    score: 92,
    temp: "hot",
  },
  {
    id: "l-2",
    name: "Hudson Valley Roofers",
    address: "221 W 78th St, New York, NY",
    rating: 4.5,
    score: 81,
    temp: "hot",
  },
  {
    id: "l-3",
    name: "Brooklyn Roof Works",
    address: "88 Metropolitan Ave, Brooklyn",
    rating: 4.3,
    score: 74,
    temp: "warm",
  },
  {
    id: "l-4",
    name: "Apex Urban Roofing",
    address: "909 3rd Ave, Manhattan",
    rating: 4.9,
    score: 88,
    temp: "hot",
  },
];
