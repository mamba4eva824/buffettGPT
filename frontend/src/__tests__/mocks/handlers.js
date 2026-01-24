/**
 * MSW Request Handlers
 *
 * Mock handlers for SSE streams and research API endpoints.
 */
import { http, HttpResponse } from 'msw';
import {
  createSSEStream,
  MOCK_TOC,
  MOCK_RATINGS,
  MOCK_SECTION_DATA
} from './researchFixtures';

const API_BASE = 'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev';

export const handlers = [
  // Health check endpoint
  http.get(`${API_BASE}/health`, () => {
    return HttpResponse.json({ status: 'healthy' });
  }),

  // SSE Stream endpoint for research reports
  http.get(`${API_BASE}/research/report/:ticker/stream`, ({ params }) => {
    const { ticker } = params;
    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        // Event 1: connected
        controller.enqueue(encoder.encode('event: connected\ndata: {}\n\n'));

        // Small delay to simulate network
        await delay(10);

        // Event 2: executive_meta
        const metaPayload = {
          toc: MOCK_TOC,
          ratings: MOCK_RATINGS,
          total_word_count: 15000,
          generated_at: new Date().toISOString()
        };
        controller.enqueue(encoder.encode(`event: executive_meta\ndata: ${JSON.stringify(metaPayload)}\n\n`));

        await delay(10);

        // Event 3-5: First section (executive summary)
        const section = MOCK_SECTION_DATA['01_executive_summary'];
        controller.enqueue(encoder.encode(`event: section_start\ndata: ${JSON.stringify({
          section_id: '01_executive_summary',
          title: section.title,
          part: section.part,
          icon: section.icon,
          word_count: section.word_count
        })}\n\n`));

        await delay(5);

        // Split content into chunks
        const chunks = chunkString(section.content, 256);
        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(`event: section_chunk\ndata: ${JSON.stringify({
            section_id: '01_executive_summary',
            text: chunk
          })}\n\n`));
          await delay(2);
        }

        controller.enqueue(encoder.encode(`event: section_end\ndata: ${JSON.stringify({
          section_id: '01_executive_summary'
        })}\n\n`));

        await delay(10);

        // Event: complete
        controller.enqueue(encoder.encode('event: complete\ndata: {}\n\n'));

        controller.close();
      }
    });

    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
      }
    });
  }),

  // Get individual section endpoint
  http.get(`${API_BASE}/research/report/:ticker/section/:sectionId`, ({ params }) => {
    const { ticker, sectionId } = params;
    const section = MOCK_SECTION_DATA[sectionId];

    if (!section) {
      return HttpResponse.json({ error: 'Section not found' }, { status: 404 });
    }

    return HttpResponse.json({
      section_id: sectionId,
      title: section.title,
      content: section.content,
      part: section.part,
      icon: section.icon,
      word_count: section.word_count
    });
  }),

  // Report status endpoint
  http.get(`${API_BASE}/research/report/:ticker/status`, ({ params }) => {
    const { ticker } = params;
    return HttpResponse.json({
      exists: true,
      expired: false,
      ttl_remaining_days: 25,
      generated_at: new Date().toISOString(),
      total_word_count: 15000
    });
  }),

  // Follow-up endpoint (POST with SSE response)
  http.post(`${API_BASE}/research/followup`, async ({ request }) => {
    const body = await request.json();
    const { ticker, question, section_id } = body;
    const encoder = new TextEncoder();
    const messageId = `msg-${Date.now()}`;

    const stream = new ReadableStream({
      async start(controller) {
        // followup_start
        controller.enqueue(encoder.encode(`event: followup_start\ndata: ${JSON.stringify({
          message_id: messageId
        })}\n\n`));

        await delay(10);

        // followup_chunk (simulated response)
        const response = `Based on the ${section_id || 'report'} for ${ticker}, here's my analysis of "${question}": This is a mock response.`;
        const chunks = chunkString(response, 50);

        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(`event: followup_chunk\ndata: ${JSON.stringify({
            message_id: messageId,
            text: chunk
          })}\n\n`));
          await delay(5);
        }

        // followup_end
        controller.enqueue(encoder.encode(`event: followup_end\ndata: ${JSON.stringify({
          message_id: messageId
        })}\n\n`));

        controller.close();
      }
    });

    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache'
      }
    });
  })
];

// Helper functions
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function chunkString(str, size) {
  const chunks = [];
  for (let i = 0; i < str.length; i += size) {
    chunks.push(str.slice(i, i + size));
  }
  return chunks;
}

// Error handlers for testing error scenarios
export const errorHandlers = {
  unauthorized: http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
    return HttpResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }),

  rateLimited: http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
    return HttpResponse.json({
      error: 'Rate limit exceeded',
      retry_after: 3600
    }, { status: 429 });
  }),

  serverError: http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
    return HttpResponse.json({ error: 'Internal server error' }, { status: 500 });
  }),

  networkError: http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
    return HttpResponse.error();
  }),

  malformedSSE: http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: connected\ndata: {}\n\n'));
        controller.enqueue(encoder.encode('event: executive_meta\ndata: {invalid json\n\n'));
        controller.close();
      }
    });
    return new HttpResponse(stream, {
      headers: { 'Content-Type': 'text/event-stream' }
    });
  }),

  sseError: http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: connected\ndata: {}\n\n'));
        controller.enqueue(encoder.encode('event: error\ndata: {"message":"Report generation failed"}\n\n'));
        controller.close();
      }
    });
    return new HttpResponse(stream, {
      headers: { 'Content-Type': 'text/event-stream' }
    });
  })
};
