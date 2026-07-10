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
// reviewArticle, or technicalNotes).
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
    description:
      "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim",
    doi: "10.12345/JTEAD.v1.1",
    issnOnline: "XXXX-XXXX",
    issnPrint: "XXXX-XXXX",
    frequency: "Semi-annual",
    articles: {
      editorialBoard: [
        {
          title: "Editorial Message from the Editor-in-Chief",
          authors: "Jemwel B. Aron",
          pdf: "assets/pdfs/editorial-message.pdf",
        },
      ],
      originalArticles: [
        {
          title: "Advances in carbon capture and utilization of technologies: A review",
          authors: "Marial L. Santos, Ariel P. Reyes, Josh B. Villanueva",
          pdf: "assets/pdfs/original-article-carbon-capture.pdf",
        },
      ],
      reviewArticle: [
        {
          title: "Advances in carbon capture and utilization of technologies: A review",
          authors: "Marial L. Santos, Ariel P. Reyes, Josh B. Villanueva",
          pdf: "assets/pdfs/review-article-carbon-capture.pdf",
        },
      ],
      technicalNotes: [
        {
          title: "Advances in carbon capture and utilization of technologies: A review",
          authors: "Marial L. Santos, Ariel P. Reyes, Josh B. Villanueva",
          pdf: "assets/pdfs/technical-note-carbon-capture.pdf",
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
    issnOnline: "XXXX-XXXX",
    issnPrint: "XXXX-XXXX",
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
    issnOnline: "XXXX-XXXX",
    issnPrint: "XXXX-XXXX",
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
    issnOnline: "XXXX-XXXX",
    issnPrint: "XXXX-XXXX",
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

// Flattens the current issue's article sections into one list, in the same
// order they appear on current.html, for the homepage "Recent Articles"
// teaser. Add a new article to any section in ISSUES and it shows up here
// automatically — no HTML editing needed.
function getRecentArticles(limit) {
  const issue = getCurrentIssue();
  const sections = [
    { key: "editorialBoard", tag: "Editorial Message" },
    { key: "originalArticles", tag: "Original research.." },
    { key: "reviewArticle", tag: "Review Article.." },
    { key: "technicalNotes", tag: "Technical Note.." },
  ];

  const pool = [];
  sections.forEach(({ key, tag }) => {
    (issue.articles[key] || []).forEach((article) => pool.push({ ...article, tag }));
  });

  return typeof limit === "number" ? pool.slice(0, limit) : pool;
}
