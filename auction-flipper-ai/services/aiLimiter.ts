import Bottleneck from 'bottleneck';

// Shared LLM limiter for all generateContent calls
export const llmLimiter = new Bottleneck({
  maxConcurrent: 2,
  minTime: 250, // ~4 requests/sec
});

/**
 * Schedule a function that returns a Promise through the shared limiter.
 * Usage: limitedSchedule(() => ai.models.generateContent(params))
 */
export const limitedSchedule = async <T>(fn: () => Promise<T>): Promise<T> => {
  return llmLimiter.schedule(fn);
};
