import { GoogleGenAI, Type, Schema } from "@google/genai";
import { AuctionItem, MarketResearch, AnalyzedItem } from "../types";
import { MARKET_RESEARCH_SYSTEM_INSTRUCTION, DEEP_ANALYSIS_SYSTEM_INSTRUCTION, CHAT_SYSTEM_INSTRUCTION } from "../constants";
import { searchEbayForItems, searchGoogleSerpForItems, Comp } from './sourceAdapters';
import { limitedSchedule } from './aiLimiter';

// Initialize Gemini Client
// NOTE: Process.env.API_KEY is injected by the environment.
const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

/**
 * Helper to clean and parse JSON from model output which might contain Markdown code blocks.
 */
const cleanAndParseJSON = (text: string | undefined): any => {
  if (!text) return {};
  try {
    // Remove markdown code blocks ```json ... ``` or just ``` ... ```
    let cleanText = text.replace(/```json\s*([\s\S]*?)\s*```/g, "$1");
    cleanText = cleanText.replace(/```\s*([\s\S]*?)\s*```/g, "$1");
    // Remove potential leading/trailing whitespace
    cleanText = cleanText.trim();
    return JSON.parse(cleanText);
  } catch (error) {
    console.error("JSON Parse Error:", error, "Original Text:", text);
    // Fallback: try to find start and end of JSON object
    try {
      const startIndex = text.indexOf('{');
      const endIndex = text.lastIndexOf('}');
      if (startIndex !== -1 && endIndex !== -1) {
        return JSON.parse(text.substring(startIndex, endIndex + 1));
      }
    } catch (e) {
      console.error("Fallback JSON Parse Error:", e);
    }
    return {};
  }
};

/**
 * Performs fast category and condition estimation using Gemini 2.5 Flash.
 * Good for initial CSV cleanup.
 */
export const quickScanItem = async (item: AuctionItem): Promise<{ category: string; condition: string }> => {
  try {
    const prompt = `
      Analyze this auction item title and description.
      Title: ${item.title}
      Description: ${item.description}
      
      Determine the likely Category (e.g., Electronics, Home, Tools) and Condition (New, Used, Parts).
      Return JSON: { "category": string, "condition": string }
    `;

    const response = await limitedSchedule(() => ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            category: { type: Type.STRING },
            condition: { type: Type.STRING },
          },
        } as Schema
      }
    }));

    return cleanAndParseJSON(response.text);
  } catch (error) {
    console.error("Quick Scan Error:", error);
    return { category: 'Unknown', condition: 'Unknown' };
  }
};

/**
 * Batch quick-scan for many items in a single model call.
 * Reduces per-call quota pressure by converting N calls -> 1 call.
 * Returns an array of { category, condition } matching the input order.
 */
export const quickScanItems = async (items: AuctionItem[]): Promise<Array<{ category: string; condition: string }>> => {
  if (!items || items.length === 0) return [];

  try {
    // Build a compact payload to send to the model
    const payload = items.map((it, idx) => ({ idx, title: it.title || '', description: it.description || '' }));

    const prompt = `
Analyze the following list of auction items. For each item return JSON object with the original index (idx),
the estimated Category (e.g., Electronics, Home, Tools) and Condition (New, Used, Parts).
Return a JSON array of objects like: [{"idx":0,"category":"...","condition":"..."}, ...]

Items: ${JSON.stringify(payload)}
`;

    const response = await limitedSchedule(() => ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: prompt,
      config: {
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              idx: { type: Type.NUMBER },
              category: { type: Type.STRING },
              condition: { type: Type.STRING }
            },
            required: ['idx', 'category', 'condition']
          }
        } as Schema
      }
    }));

    const data = cleanAndParseJSON(response.text);

    // If parse didn't produce an array, fall back to per-item quick scan
    if (!Array.isArray(data)) {
      throw new Error('Batch quickScan returned invalid JSON, falling back to per-item calls');
    }

    // Map results by idx for ordering; provide defaults for missing entries
    const map = new Map<number, { category: string; condition: string }>();
    data.forEach((obj: any) => {
      if (obj && typeof obj.idx === 'number') {
        map.set(obj.idx, { category: obj.category || 'Unknown', condition: obj.condition || 'Unknown' });
      }
    });

    return items.map((_, i) => map.get(i) || { category: 'Unknown', condition: 'Unknown' });

  } catch (err) {
    console.error('Batch quickScan error, falling back to per-item quickScan:', err);
    // Fallback: run sequential per-item scans (slower but reliable)
    const results: Array<{ category: string; condition: string }> = [];
    for (const it of items) {
      try {
        // reuse existing quickScanItem
        // eslint-disable-next-line no-await-in-loop
        const r = await quickScanItem(it);
        results.push({ category: r.category || 'Unknown', condition: r.condition || 'Unknown' });
      } catch (e) {
        results.push({ category: 'Unknown', condition: 'Unknown' });
      }
    }
    return results;
  }
};

/**
 * Performs deep market research using Gemini 2.5 Flash + Google Search.
 */
export const researchItemMarket = async (item: AuctionItem): Promise<MarketResearch> => {
  const prompt = `
    Research market data for:
    Item: ${item.title}
    Description: ${item.description}
    Condition: ${item.condition}
    
    Find:
    1. Average Retail Price (New)
    2. Average Sold Price (Used/Similar Condition) - Check eBay/Mercari sold listings via search.
    3. Demand Score (1-10)
    4. Liquidity Score (1-10)
    
    If exact match not found, estimate based on similar models.
  `;

    const response = await limitedSchedule(() => ai.models.generateContent({
    model: 'gemini-2.5-flash',
    contents: prompt,
    config: {
      tools: [{ googleSearch: {} }],
      systemInstruction: MARKET_RESEARCH_SYSTEM_INSTRUCTION,
      responseMimeType: "application/json",
      responseSchema: {
        type: Type.OBJECT,
        properties: {
          retailPrice: { type: Type.NUMBER, description: "Current new retail price" },
          usedPrice: { type: Type.NUMBER, description: "Average used sold price" },
          ebaySoldAvg: { type: Type.NUMBER, description: "Average sold price on eBay for this condition" },
          demandScore: { type: Type.NUMBER, description: "1-10 score of market demand" },
          liquidityScore: { type: Type.NUMBER, description: "1-10 score of sales velocity" },
          conditionNotes: { type: Type.STRING, description: "Notes on how condition affects value" },
        },
        required: ["retailPrice", "usedPrice", "ebaySoldAvg", "demandScore", "liquidityScore"]
      } as Schema
    }
  }));

  const data = cleanAndParseJSON(response.text);
  
  // Extract grounding links if available
  const links: string[] = [];
  const chunks = response.candidates?.[0]?.groundingMetadata?.groundingChunks;
  if (chunks) {
    chunks.forEach((chunk: any) => {
      if (chunk.web?.uri) links.push(chunk.web.uri);
    });
  }

  return {
    ...data,
    compLinks: links,
    lastUpdated: new Date().toISOString()
  };
};

/**
 * Batch market research for multiple items in a single model call.
 * By default this runs in a lightweight mode (useSearch=false) that does NOT perform web grounding/searching.
 * Set useSearch=true to enable grounding tools (slower, higher quota impact).
 */
export const batchResearchItems = async (items: AuctionItem[], useSearch = false): Promise<MarketResearch[]> => {
  if (!items || items.length === 0) return [];

  try {
    const payload = items.map((it, idx) => ({ idx, title: it.title || '', description: it.description || '', condition: it.condition || '' }));

    // When useSearch=true, run SERP adapter first, then selectively call eBay adapter
    let perItemComps: Record<number, Comp[]> = {};
    let ebayFallbackCount = 0;
    let serpProvidedEbayCount = 0;
    const EBAY_THRESHOLD = 2; // if SERP returns fewer than this many eBay comps, consider fallback
    const EBAY_PREFERRED_CATEGORIES = ['collectibles', 'parts', 'electronics', 'tools', 'automotive', 'industrial', 'antiques'];

    if (useSearch) {
      // Run SERP adapter first (primary)
      const serpResults = await searchGoogleSerpForItems(payload, 3);

      // Initialize perItemComps
      payload.forEach(p => {
        perItemComps[p.idx] = [];
      });

      // Merge SERP comps
      serpResults.forEach(r => {
        perItemComps[r.idx] = perItemComps[r.idx].concat(r.comps || []);
      });

      // Decide which items need eBay fallback
      const needsEbay: { idx: number; title: string }[] = [];
      payload.forEach(p => {
        const comps = perItemComps[p.idx] || [];
        const ebayCount = comps.filter(c => c.url && /\bebay\.(com|co\.uk|ca|com\.au)\b/i.test(c.url)).length;
        if (ebayCount >= EBAY_THRESHOLD) {
          serpProvidedEbayCount += 1;
        } else {
          // Check if this category historically relies on eBay
          const cat = (p as any).category || '';
          const catLower = String(cat).toLowerCase();
          const prefersEbay = EBAY_PREFERRED_CATEGORIES.some(k => catLower.includes(k));
          if (prefersEbay) {
            needsEbay.push({ idx: p.idx, title: p.title });
          }
        }
      });

      // If any items need eBay fallback, call the eBay adapter only for that subset
      if (needsEbay.length > 0) {
        ebayFallbackCount = needsEbay.length;
        const ebayResults = await searchEbayForItems(needsEbay.map(n => ({ idx: n.idx, title: n.title })), 3);
        ebayResults.forEach(r => {
          perItemComps[r.idx] = perItemComps[r.idx].concat(r.comps || []);
        });
      }

      // Log summary
      console.info(`batchResearchItems: SERP provided ebay comps for ${serpProvidedEbayCount}/${payload.length} items; eBay fallback used for ${ebayFallbackCount} items`);
    }

    // Build summarization prompt that includes comps when available
    const compactItems = payload.map(p => ({ idx: p.idx, title: p.title }));
    const compSection = useSearch ? `\nComps per item: ${JSON.stringify(perItemComps)}` : '';

    const prompt = `For each item in the provided list, estimate market research values. Return a JSON array of objects with these fields:\n{ "idx": <original index>, "retailPrice": number, "usedPrice": number, "ebaySoldAvg": number, "demandScore": number (1-10), "liquidityScore": number (1-10), "conditionNotes": string }\n\nItems: ${JSON.stringify(compactItems)}${compSection}`;

    const config: any = {
      responseMimeType: 'application/json',
      responseSchema: {
        type: Type.ARRAY,
        items: {
          type: Type.OBJECT,
          properties: {
            idx: { type: Type.NUMBER },
            retailPrice: { type: Type.NUMBER },
            usedPrice: { type: Type.NUMBER },
            ebaySoldAvg: { type: Type.NUMBER },
            demandScore: { type: Type.NUMBER },
            liquidityScore: { type: Type.NUMBER },
            conditionNotes: { type: Type.STRING }
          },
          required: ['idx','retailPrice','usedPrice','ebaySoldAvg','demandScore','liquidityScore']
        }
      } as Schema
    };

    if (useSearch) {
      config.systemInstruction = MARKET_RESEARCH_SYSTEM_INSTRUCTION;
    }

    const response = await limitedSchedule(() => ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: prompt,
      config
    }));

    const data = cleanAndParseJSON(response.text);
    if (!Array.isArray(data)) throw new Error('Batch research returned invalid JSON');

    const map = new Map<number, any>();
    data.forEach((obj: any) => {
      if (obj && typeof obj.idx === 'number') {
        map.set(obj.idx, obj);
      }
    });

    const now = new Date().toISOString();
    return items.map((_, i) => {
      const obj = map.get(i) || {};
      const comps = perItemComps[i] || [];
      const compLinks = comps.map(c => c.url).filter(Boolean) as string[];
      return {
        retailPrice: typeof obj.retailPrice === 'number' ? obj.retailPrice : 0,
        usedPrice: typeof obj.usedPrice === 'number' ? obj.usedPrice : 0,
        ebaySoldAvg: typeof obj.ebaySoldAvg === 'number' ? obj.ebaySoldAvg : 0,
        demandScore: typeof obj.demandScore === 'number' ? obj.demandScore : 5,
        liquidityScore: typeof obj.liquidityScore === 'number' ? obj.liquidityScore : 5,
        conditionNotes: obj.conditionNotes || '',
        compLinks: compLinks,
        lastUpdated: now
      } as MarketResearch;
    });

  } catch (err) {
    console.error('Batch research error, falling back to per-item research:', err);
    const results: MarketResearch[] = [];
    for (const it of items) {
      try {
        // eslint-disable-next-line no-await-in-loop
        const r = await researchItemMarket(it);
        results.push(r);
      } catch (e) {
        results.push({ retailPrice:0, usedPrice:0, ebaySoldAvg:0, demandScore:5, liquidityScore:5, conditionNotes:'', compLinks:[], lastUpdated: new Date().toISOString() });
      }
    }
    return results;
  }
};

/**
 * Performs a deep "Thinking" analysis for risk assessment using Gemini 2.5 Flash.
 */
export const performDeepRiskAnalysis = async (item: AnalyzedItem): Promise<string> => {
  const prompt = `
    Perform a deep risk analysis for this arbitrage opportunity.
    
    Item: ${item.title}
    Current Bid: $${item.currentBid}
    Estimated Sell Price: $${item.profitAnalysis?.estimatedSellPrice}
    Market Data: ${JSON.stringify(item.marketResearch)}
    
    Identify specific risks regarding shipping, returns, scam potential, and technical failure rates.
  `;

  const response = await limitedSchedule(() => ai.models.generateContent({
    model: 'gemini-2.5-flash',
    contents: prompt,
    config: {
      systemInstruction: DEEP_ANALYSIS_SYSTEM_INSTRUCTION,
      thinkingConfig: { thinkingBudget: 16384 } // Adjusted for Flash model capabilities
    }
  }));

  return response.text || "Analysis failed.";
};

/**
 * Chat with the AI about the dataset using Gemini 2.5 Flash.
 */
export const chatWithAI = async (history: {role: string, parts: {text: string}[]}[], contextData: string) => {
  // We use generateContent to maintain stateless control over the context injection.
  // The structure will be:
  // 1. User: Context Data
  // 2. Model: "Okay I understand" (Implicitly handled by history start if needed, but here we just prepend context)
  // To avoid role errors, we ensure the first message is user.
  
  const contents = [
    { role: 'user', parts: [{ text: `SYSTEM CONTEXT - DATASET SUMMARY:\n${contextData}` }] },
    ...history.map(h => ({ role: h.role, parts: h.parts }))
  ];

  const response = await limitedSchedule(() => ai.models.generateContent({
    model: 'gemini-2.5-flash',
    contents: contents,
    config: {
      systemInstruction: CHAT_SYSTEM_INSTRUCTION,
    }
  }));

  return response.text;
};