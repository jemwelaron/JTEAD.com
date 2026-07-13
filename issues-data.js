// All published issues of JTEAD — the single source of truth for
// current.html (via getCurrentIssue) and archives.html.
//
// To publish a new issue: add an object to this array and set its
// `current: true` (switch the previous issue's `current` to false).
// current.html and archives.html both pick this up automatically —
// no other file needs to change.
//
// To publish a new article within an existing issue: add an object to
// that issue's matching articles array (editorialBoard, originalArticles,
// reviewArticle, or technicalNotes). Each article can optionally set
// `thumb` (a path under IMAGE/articles/) for its thumbnail on the
// homepage's "Recent Articles" teaser — if omitted, or if the file
// doesn't exist yet, a plain gray box is shown instead.
//
// Every article needs a unique `id` (any string, just unique across the
// whole file) — that's what article.html?id=... uses to look it up via
// getArticleContext(). `abstract`, `keywords`, and `doi` are optional;
// article.html shows an honest "not yet added"/"Pending" fallback for
// whichever ones are omitted, same convention as the issue-level fields.
const ISSUES = [
  {
    id: "2025-v1-n1",
    volume: 1,
    number: 1,
    year: 2025,
    monthLabel: "June 2025",
    publishedDate: "2025-06-30",
    publishedLabel: "June 30, 2025",
    current: true,
    cover: "IMAGE/2025-v1-n1-cover.jpg",
    description: "Details for this issue have not been added yet.",
    doi: "10.12345/JTEAD.v1.1",
    issnOnline: "Pending",
    issnPrint: "Pending",
    frequency: "Semi-annual",
    articles: {
      editorialBoard: [
        {
          id: "editorial-message-2025-v1-n1",
          title: "Editorial Message from the Editor-in-Chief",
          authors: "Nolan C. Tolosa",
          pdf: "assets/pdfs/editorial-message.pdf",
          thumb: "IMAGE/articles/editorial-message.jpg",
          doi: "10.12345/JTEAD.v1.1.001",
        },
      ],
      originalArticles: [
        {
          id: "original-article-carbon-capture-2025-v1-n1",
          title: "Advances in carbon capture and utilization of technologies: A review",
          authors: "Marial L. Santos, Ariel P. Reyes, Josh B. Villanueva",
          pdf: "assets/pdfs/original-article-carbon-capture.pdf",
          thumb: "IMAGE/articles/original-article-carbon-capture.jpg",
          doi: "10.12345/JTEAD.v1.1.002",
        },
      ],
      reviewArticle: [
        {
          id: "review-article-carbon-capture-2025-v1-n1",
          title: "Advances in carbon capture and utilization of technologies: A review",
          authors: "Marial L. Santos, Ariel P. Reyes, Josh B. Villanueva",
          pdf: "assets/pdfs/review-article-carbon-capture.pdf",
          thumb: "IMAGE/articles/review-article-carbon-capture.jpg",
          doi: "10.12345/JTEAD.v1.1.003",
        },
      ],
      technicalNotes: [
        {
          id: "technical-note-carbon-capture-2025-v1-n1",
          title: "Advances in carbon capture and utilization of technologies: A review",
          authors: "Marial L. Santos, Ariel P. Reyes, Josh B. Villanueva",
          pdf: "assets/pdfs/technical-note-carbon-capture.pdf",
          thumb: "IMAGE/articles/technical-note-carbon-capture.jpg",
          doi: "10.12345/JTEAD.v1.1.004",
        },
      ],
    },
  },
  {
    id: "2025-v1-n2",
    volume: 1,
    number: 2,
    year: 2025,
    monthLabel: "December 2025",
    publishedDate: "2025-12-30",
    publishedLabel: "December 30, 2025",
    current: false,
    cover: "IMAGE/2025-v1-n2-cover.jpg",
    description: "Details for this issue have not been added yet.",
    doi: "10.12345/JTEAD.v1.2",
    issnOnline: "Pending",
    issnPrint: "Pending",
    frequency: "Semi-annual",
    articles: {
      editorialBoard: [],
      originalArticles: [],
      reviewArticle: [],
      technicalNotes: [],
    },
  },
  {
    id: "2026-v1-n1",
    volume: 1,
    number: 1,
    year: 2026,
    monthLabel: "June 2026",
    publishedDate: "2026-06-30",
    publishedLabel: "June 30, 2026",
    current: false,
    cover: "IMAGE/2026-v1-n1-cover.jpg",
    description: "Details for this issue have not been added yet.",
    doi: "10.12345/JTEAD.v2.1",
    issnOnline: "Pending",
    issnPrint: "Pending",
    frequency: "Semi-annual",
    articles: {
      editorialBoard: [],
      originalArticles: [],
      reviewArticle: [],
      technicalNotes: [],
    },
  },
  {
    id: "2026-v1-n2",
    volume: 1,
    number: 2,
    year: 2026,
    monthLabel: "December 2026",
    publishedDate: "2026-12-30",
    publishedLabel: "December 30, 2026",
    current: false,
    cover: "IMAGE/2026-v1-n2-cover.jpg",
    description: "Details for this issue have not been added yet.",
    doi: "10.12345/JTEAD.v2.2",
    issnOnline: "Pending",
    issnPrint: "Pending",
    frequency: "Semi-annual",
    articles: {
      editorialBoard: [],
      originalArticles: [],
      reviewArticle: [],
      technicalNotes: [],
    },
  },
];

// Returns the issue flagged `current: true` (first match wins). Falls back
// to the most recently published issue if none is flagged, so the page
// never breaks even if the flag is left unset.
function getCurrentIssue() {
  const flagged = ISSUES.find((issue) => issue.current);
  if (flagged) return flagged;

  return [...ISSUES].sort((a, b) => new Date(b.publishedDate) - new Date(a.publishedDate))[0];
}

function getIssueById(id) {
  return ISSUES.find((issue) => issue.id === id);
}

const ARTICLE_SECTIONS = [
  { key: "editorialBoard", tag: "Editorial Message" },
  { key: "originalArticles", tag: "Original research.." },
  { key: "reviewArticle", tag: "Review Article.." },
  { key: "technicalNotes", tag: "Technical Note.." },
];

// Flattens one issue's article sections into a single list (in the order
// they appear on current.html), each tagged with its section label.
function getIssueArticles(issue) {
  const pool = [];
  ARTICLE_SECTIONS.forEach(({ key, tag }) => {
    (issue.articles[key] || []).forEach((article) => pool.push({ ...article, tag }));
  });
  return pool;
}

// Flattens the current issue's article sections into one list, for the
// homepage "Recent Articles" teaser. Add a new article to any section in
// ISSUES and it shows up here automatically — no HTML editing needed.
function getRecentArticles(limit) {
  const pool = getIssueArticles(getCurrentIssue());
  return typeof limit === "number" ? pool.slice(0, limit) : pool;
}

// Looks up a single article by its `id` across every issue, for
// article.html. Returns { article, issue } (with `article.tag` set to its
// section label) or null if no article anywhere has that id.
function getArticleContext(id) {
  for (const issue of ISSUES) {
    const match = getIssueArticles(issue).find((article) => article.id === id);
    if (match) return { article: match, issue };
  }
  return null;
}
