import { GoogleGenAI, Type, Schema } from "@google/genai";
import { limitedSchedule } from './aiLimiter';

// Simple comp shape
export type Comp = {
  source: string;
  price: number;
  currency: string;
  condition?: string;
  url?: string;
  date?: string;
};

// Initialize a separate client for adapters (uses same env API key)
const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

/**
 * Search eBay (via Google Search tool) for each item and return up to `max` comps per item.
 * Returns an array where each element corresponds to input item index: { idx, comps: Comp[] }
 * This is a lightweight, AI-driven adapter that uses the googleSearch tool rather than scraping directly.
 */
export const searchEbayForItems = async (
  items: { idx: number; title: string; description?: string }[],
  max = 3
): Promise<Array<{ idx: number; comps: Comp[] }>> => {
  if (!items || items.length === 0) return [];

  const payload = items.map(i => ({ idx: i.idx, title: i.title }));

  const prompt = `For each item below, search eBay (site:ebay.com) and return up to ${max} recent sold or active listings that match the title.
Return a JSON array of objects: {"idx": <original idx>, "comps": [{"price": number, "currency":"USD", "condition":"Used|New|Refurb|Parts", "url":"...", "date":"YYYY-MM-DD"}, ...] }

Items: ${JSON.stringify(payload)}`;

  try {
    const response = await limitedSchedule(() => ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: prompt,
      config: {
        tools: [{ googleSearch: {} }],
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              idx: { type: Type.NUMBER },
              comps: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    price: { type: Type.NUMBER },
                    currency: { type: Type.STRING },
                    condition: { type: Type.STRING },
                    url: { type: Type.STRING },
                    date: { type: Type.STRING }
                  }
                }
              }
            }
          }
        } as Schema
      }
  }));

    const parsed = JSON.parse(response.text || '[]');
    // Normalize to expected shape
    return items.map(i => {
      const found = Array.isArray(parsed) ? parsed.find((p: any) => p.idx === i.idx) : null;
      const comps = (found && Array.isArray(found.comps)) ? found.comps.map((c: any) => ({
        source: 'ebay',
        price: Number(c.price) || 0,
        currency: c.currency || 'USD',
        condition: c.condition || 'Unknown',
        url: c.url,
        date: c.date
      })) : [];
      return { idx: i.idx, comps };
    });

  } catch (err) {
    console.error('eBay adapter error:', err);
    // Fallback: return empty comps
    return items.map(i => ({ idx: i.idx, comps: [] }));
  }
};

/**
 * General Google SERP adapter: runs a web search and returns compact comps per item.
 * Uses the googleSearch tool available to the model.
 */
export const searchGoogleSerpForItems = async (
  items: { idx: number; title: string; description?: string }[],
  max = 3
): Promise<Array<{ idx: number; comps: Comp[] }>> => {
  if (!items || items.length === 0) return [];

  const payload = items.map(i => ({ idx: i.idx, title: i.title }));

  const prompt = `For each item, perform a web search (Google SERP) and return up to ${max} relevant listing comps from marketplaces or classifieds. Return JSON array: {"idx":<idx>,"comps":[{"price":number,"currency":"USD","condition":"...","url":"...","date":"YYYY-MM-DD","source":"site or marketplace"}, ...]}

Items: ${JSON.stringify(payload)}`;

  try {
    const response = await limitedSchedule(() => ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: prompt,
      config: {
        tools: [{ googleSearch: {} }],
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              idx: { type: Type.NUMBER },
              comps: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    price: { type: Type.NUMBER },
                    currency: { type: Type.STRING },
                    condition: { type: Type.STRING },
                    url: { type: Type.STRING },
                    date: { type: Type.STRING },
                    source: { type: Type.STRING }
                  }
                }
              }
            }
          }
        } as Schema
      }
  }));

    const parsed = JSON.parse(response.text || '[]');
    return items.map(i => {
      const found = Array.isArray(parsed) ? parsed.find((p: any) => p.idx === i.idx) : null;
      const comps = (found && Array.isArray(found.comps)) ? found.comps.map((c: any) => ({
        source: c.source || 'web',
        price: Number(c.price) || 0,
        currency: c.currency || 'USD',
        condition: c.condition || 'Unknown',
        url: c.url,
        date: c.date
      })) : [];
      return { idx: i.idx, comps };
    });

  } catch (err) {
    console.error('Google SERP adapter error:', err);
    return items.map(i => ({ idx: i.idx, comps: [] }));
  }
};
