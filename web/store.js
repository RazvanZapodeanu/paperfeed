const KEY = "paperfeed";

function empty() {
  return { feed: null, fetchedAt: 0, done: [], saved: [], hinted: false };
}

export function load() {
  try {
    return { ...empty(), ...JSON.parse(localStorage.getItem(KEY)) };
  } catch {
    return empty();
  }
}

export function save(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // Storage can be full or blocked. The app keeps working for this session.
  }
}
