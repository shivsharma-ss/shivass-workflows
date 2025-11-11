const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || '').replace(/\/$/, '');

function buildUrl(path) {
  if (!API_BASE) {
    return path;
  }
  return `${API_BASE}${path}`;
}

async function parseJson(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    console.warn('Failed to parse JSON response', error);
    return null;
  }
}

export async function fetchAnalyses(limit = 50, signal) {
  const response = await fetch(buildUrl(`/v1/analyses?limit=${limit}`), {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
    cache: 'no-store',
    signal,
  });

  if (!response.ok) {
    throw new Error('Failed to fetch analyses');
  }

  const payload = await parseJson(response);
  return payload?.items || [];
}

export async function fetchAnalysisStatus(analysisId, signal) {
  const response = await fetch(buildUrl(`/v1/analyses/${analysisId}`), {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
    cache: 'no-store',
    signal,
  });

  if (!response.ok) {
    throw new Error('Failed to fetch analysis status');
  }

  return parseJson(response);
}

export async function fetchArtifacts(analysisId, signal) {
  const response = await fetch(buildUrl(`/v1/analyses/${analysisId}/artifacts`), {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
    cache: 'no-store',
    signal,
  });

  if (!response.ok) {
    throw new Error('Failed to fetch artifacts');
  }

  const payload = await parseJson(response);
  return payload || [];
}

export async function createAnalysis({
  email,
  cvDocId,
  jobDescription,
  jobDescriptionUrl,
}) {
  const response = await fetch(buildUrl('/v1/analyses'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      userEmail: email,
      cvDocId,
      jobDescription: jobDescription || null,
      jobDescriptionUrl: jobDescriptionUrl || null,
    }),
  });

  if (!response.ok) {
    const errorBody = await parseJson(response);
    const message = errorBody?.detail || 'Failed to create analysis';
    throw new Error(message);
  }

  return parseJson(response);
}
