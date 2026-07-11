document.addEventListener("DOMContentLoaded", () => {
  /* ---------- Site-wide account link (login state) ----------
   * Pages like my-submissions.html and editor-dashboard.html already manage
   * #accountLink themselves (they require auth, so they set href="#" up
   * front). This only touches pages that still show the untouched default
   * "My Account" -> authentication.html link, so it never double-handles
   * the element or attaches a second logout listener on top of theirs. */
  const accountLink = document.getElementById("accountLink");

  if (accountLink && accountLink.getAttribute("href") === "authentication.html") {
    fetch("/api/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((me) => {
        if (!me) return;

        let destination = "my-submissions.html";
        let destinationLabel = "My Submissions";
        if (me.is_editor) {
          destination = "editor-dashboard.html";
          destinationLabel = "Editor Dashboard";
        } else if (me.is_reviewer) {
          destination = "reviewer-dashboard.html";
          destinationLabel = "Reviewer Dashboard";
        }
        accountLink.textContent = destinationLabel;
        accountLink.href = destination;

        accountLink.insertAdjacentHTML("afterend", ' <a href="#" id="logoutLink">Log Out</a>');
        document.getElementById("logoutLink").addEventListener("click", async (e) => {
          e.preventDefault();
          const csrfRes = await fetch("/api/csrf-token");
          const { csrf_token } = await csrfRes.json();
          await fetch("/api/logout", { method: "POST", headers: { "X-CSRFToken": csrf_token } });
          window.location.reload();
        });
      })
      .catch(() => {});
  }

  /* ---------- Homepage: announcements ---------- */
  const announceList = document.getElementById("announceList");

  if (announceList && typeof ANNOUNCEMENTS !== "undefined") {
    const visibleCount = typeof ANNOUNCEMENTS_VISIBLE === "number" ? ANNOUNCEMENTS_VISIBLE : ANNOUNCEMENTS.length;

    announceList.innerHTML = ANNOUNCEMENTS.slice(0, visibleCount)
      .map(
        (item) => `
          <div class="announce-item">
            <h4>${item.icon} ${item.title}</h4>
            <p>${item.text}</p>
          </div>`
      )
      .join("");
  }

  /* ---------- Announcements page: full list ---------- */
  const announcementsPageList = document.getElementById("announcementsPageList");

  if (announcementsPageList && typeof ANNOUNCEMENTS !== "undefined") {
    announcementsPageList.innerHTML = ANNOUNCEMENTS.map(
      (item) => `
        <div class="card">
          <div class="announce-item">
            <h4>${item.icon} ${item.title}</h4>
            <p>${item.text}</p>
          </div>
        </div>`
    ).join("");
  }

  /* ---------- Site search ---------- */
  const searchInput = document.getElementById("siteSearchInput");
  const searchResults = document.getElementById("searchResults");

  if (searchInput && searchResults && typeof ISSUES !== "undefined") {
    const SEARCH_SECTIONS = [
      { key: "editorialBoard", tag: "Editorial Message" },
      { key: "originalArticles", tag: "Original research.." },
      { key: "reviewArticle", tag: "Review Article.." },
      { key: "technicalNotes", tag: "Technical Note.." },
    ];

    const getAllArticles = () => {
      const pool = [];
      ISSUES.forEach((issue) => {
        SEARCH_SECTIONS.forEach(({ key, tag }) => {
          (issue.articles[key] || []).forEach((article) => {
            pool.push({
              ...article,
              tag,
              issueId: issue.id,
              issueLabel: `Vol. ${issue.volume}, No. ${issue.number} (${issue.monthLabel})`,
            });
          });
        });
      });
      return pool;
    };

    const closeSearch = () => {
      searchResults.classList.remove("is-open");
    };

    const runSearch = () => {
      const query = searchInput.value.trim().toLowerCase();

      if (!query) {
        closeSearch();
        searchResults.innerHTML = "";
        return;
      }

      const matches = getAllArticles().filter(
        (article) => article.title.toLowerCase().includes(query) || article.authors.toLowerCase().includes(query)
      );

      searchResults.innerHTML = matches.length
        ? matches
            .slice(0, 8)
            .map(
              (article) => `
                <a class="search-result-item" href="current.html?id=${article.issueId}">
                  <p class="search-result-title">${article.title}</p>
                  <p class="search-result-meta">${article.tag} &middot; ${article.issueLabel}</p>
                </a>`
            )
            .join("")
        : '<p class="search-result-empty">No articles found.</p>';

      searchResults.classList.add("is-open");
    };

    let searchDebounce = null;
    searchInput.addEventListener("input", () => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(runSearch, 200);
    });

    searchInput.addEventListener("focus", () => {
      if (searchInput.value.trim()) runSearch();
    });

    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeSearch();
        searchInput.blur();
      }
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".search-wrap")) closeSearch();
    });
  }

  /* ---------- Editorial board ---------- */
  const renderBoardMember = (editor) => `
    <div class="board-member">
      <div class="member-avatar">
        <img src="${editor.photo}" alt="" onerror="this.style.display='none';" />
      </div>
      <div class="member-info">
        <div class="member-name"><a href="${editor.link || "#"}">${editor.name}</a></div>
        <div class="member-roles">${editor.roles}</div>
        <div class="member-affiliation">${editor.affiliation}</div>
      </div>
    </div>`;

  const editorInChiefList = document.getElementById("editorInChiefList");
  if (editorInChiefList && typeof EDITOR_IN_CHIEF !== "undefined") {
    editorInChiefList.innerHTML = EDITOR_IN_CHIEF.map(renderBoardMember).join("");
  }

  const associateEditorsList = document.getElementById("associateEditorsList");
  if (associateEditorsList && typeof ASSOCIATE_EDITORS !== "undefined") {
    associateEditorsList.innerHTML = ASSOCIATE_EDITORS.map(renderBoardMember).join("");
  }

  /* ---------- Homepage: recent articles ---------- */
  const recentArticlesList = document.getElementById("recentArticlesList");

  if (recentArticlesList && typeof getRecentArticles === "function") {
    const RECENT_ARTICLES_VISIBLE = 2;
    const recentArticles = getRecentArticles(RECENT_ARTICLES_VISIBLE);

    recentArticlesList.innerHTML = recentArticles.length
      ? recentArticles
          .map(
            (article) => `
              <article class="article-card">
                <div class="article-thumb"></div>
                <div>
                  <p class="article-tag">${article.tag}</p>
                  <h4 class="article-title"><a href="${article.pdf}" target="_blank" rel="noopener">${article.title}</a></h4>
                  <p class="article-authors">${article.authors}</p>
                </div>
              </article>`
          )
          .join("")
      : '<p class="article-row-empty">No articles published yet.</p>';
  }

  /* ---------- Homepage: hero image slider ---------- */
  const heroSlider = document.getElementById("heroSlider");

  if (heroSlider) {
    const slides = Array.from(heroSlider.querySelectorAll(".hero-slide"));
    const dots = Array.from(heroSlider.querySelectorAll(".hero-dot"));
    const AUTO_ADVANCE_MS = 5000;
    let current = slides.findIndex((slide) => slide.classList.contains("is-active"));
    if (current === -1) current = 0;
    let timer = null;

    const showSlide = (index) => {
      const next = (index + slides.length) % slides.length;
      slides[current].classList.remove("is-active");
      dots[current] && dots[current].classList.remove("is-active");
      current = next;
      slides[current].classList.add("is-active");
      dots[current] && dots[current].classList.add("is-active");
    };

    const restartTimer = () => {
      if (timer) clearInterval(timer);
      timer = setInterval(() => showSlide(current + 1), AUTO_ADVANCE_MS);
    };

    heroSlider.querySelector(".hero-slider-arrow.prev").addEventListener("click", () => {
      showSlide(current - 1);
      restartTimer();
    });

    heroSlider.querySelector(".hero-slider-arrow.next").addEventListener("click", () => {
      showSlide(current + 1);
      restartTimer();
    });

    dots.forEach((dot, index) => {
      dot.addEventListener("click", () => {
        showSlide(index);
        restartTimer();
      });
    });

    restartTimer();
  }

  /* ---------- Issue pages: hero info + article lists ---------- */
  const renderArticleSection = (id, articles) => {
    const container = document.getElementById(id);
    if (!container) return;

    if (!articles || !articles.length) {
      container.innerHTML = '<p class="article-row-empty">No articles listed for this section yet.</p>';
      return;
    }

    container.innerHTML = articles
      .map(
        (article) => `
          <div class="article-row">
            <div>
              <p class="article-row-title">${article.title}</p>
              <p class="article-row-authors">${article.authors}</p>
            </div>
            <a class="pdf-badge" href="${article.pdf}" target="_blank" rel="noopener">PDF</a>
          </div>`
      )
      .join("");
  };

  const issueTitleEl = document.getElementById("issueTitle");

  if (issueTitleEl && typeof ISSUES !== "undefined") {
    const requestedId = new URLSearchParams(window.location.search).get("id");
    const currentIssue = getCurrentIssue();
    const issue = (requestedId && getIssueById(requestedId)) || currentIssue;

    const headingEl = document.getElementById("issuePageHeading");
    if (headingEl) {
      headingEl.textContent = issue.id === currentIssue.id ? "Current issues" : `Past Issue — Vol. ${issue.volume}, No. ${issue.number}`;
    }

    const coverImg = document.getElementById("issueCoverImg");
    if (coverImg) coverImg.src = issue.cover;

    issueTitleEl.textContent = `Vol. ${issue.volume}, No. ${issue.number} (${issue.monthLabel})`;
    document.getElementById("issuePublished").textContent = `Published : ${issue.publishedLabel}`;
    document.getElementById("issueDescription").textContent = issue.description;
    document.getElementById("issueDOI").textContent = issue.doi;
    document.getElementById("issueISSNOnline").textContent = issue.issnOnline;
    document.getElementById("issueISSNPrint").textContent = issue.issnPrint;
    document.getElementById("issueFrequency").textContent = issue.frequency;

    renderArticleSection("editorialBoardList", issue.articles.editorialBoard);
    renderArticleSection("originalArticlesList", issue.articles.originalArticles);
    renderArticleSection("reviewArticleList", issue.articles.reviewArticle);
    renderArticleSection("technicalNotesList", issue.articles.technicalNotes);
  }

  /* ---------- Archives: issue list grouped by year, with filters ---------- */
  const archivesList = document.getElementById("archivesList");

  if (archivesList && typeof ISSUES !== "undefined") {
    const renderArchivesList = (issuesToRender) => {
      if (!issuesToRender.length) {
        archivesList.innerHTML = '<p class="article-row-empty">No issues match your filters.</p>';
        return;
      }

      const byYear = {};
      issuesToRender.forEach((issue) => {
        (byYear[issue.year] = byYear[issue.year] || []).push(issue);
      });

      const years = Object.keys(byYear).sort((a, b) => b - a);

      archivesList.innerHTML = years
        .map((year) => {
          const issuesForYear = [...byYear[year]].sort((a, b) => new Date(b.publishedDate) - new Date(a.publishedDate));
          const volume = issuesForYear[0].volume;

          const lines = issuesForYear
            .map(
              (issue) => `
                <div class="issue-line">
                  <div>
                    <p class="issue-line-title">No. ${issue.number} (${issue.monthLabel})</p>
                    <p class="issue-line-pub">Published: ${issue.publishedLabel}</p>
                  </div>
                  <a href="current.html?id=${issue.id}"><button class="btn-view-issue" type="button">View Issue</button></a>
                </div>`
            )
            .join("");

          return `
            <div class="year-block">
              <h3 class="year-title">${year}</h3>
              <div class="volume-toggle"><span class="arrow">&#9662;</span> Vol.${volume} (${year})</div>
              <div class="volume-body">${lines}</div>
            </div>`;
        })
        .join("");
    };

    const searchInputEl = document.getElementById("archiveSearchInput");
    const yearSelect = document.getElementById("archiveYearSelect");
    const volumeSelect = document.getElementById("archiveVolumeSelect");
    const filterBtn = document.getElementById("archiveFilterBtn");

    if (yearSelect) {
      const years = [...new Set(ISSUES.map((issue) => issue.year))].sort((a, b) => b - a);
      years.forEach((year) => {
        const option = document.createElement("option");
        option.value = year;
        option.textContent = year;
        yearSelect.appendChild(option);
      });
    }

    if (volumeSelect) {
      const volumes = [...new Set(ISSUES.map((issue) => issue.volume))].sort((a, b) => a - b);
      volumes.forEach((volume) => {
        const option = document.createElement("option");
        option.value = volume;
        option.textContent = `Vol. ${volume}`;
        volumeSelect.appendChild(option);
      });
    }

    const applyFilters = () => {
      const query = (searchInputEl && searchInputEl.value.trim().toLowerCase()) || "";
      const year = (yearSelect && yearSelect.value) || "";
      const volume = (volumeSelect && volumeSelect.value) || "";

      const filtered = ISSUES.filter((issue) => {
        const matchesYear = !year || String(issue.year) === year;
        const matchesVolume = !volume || String(issue.volume) === volume;
        const haystack = `${issue.monthLabel} no. ${issue.number} vol. ${issue.volume} ${issue.year}`.toLowerCase();
        const matchesQuery = !query || haystack.includes(query);
        return matchesYear && matchesVolume && matchesQuery;
      });

      renderArchivesList(filtered);
    };

    renderArchivesList(ISSUES);

    if (filterBtn) filterBtn.addEventListener("click", applyFilters);
    if (yearSelect) yearSelect.addEventListener("change", applyFilters);
    if (volumeSelect) volumeSelect.addEventListener("change", applyFilters);
    if (searchInputEl) {
      searchInputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          applyFilters();
        }
      });
    }
  }

  const toggle = document.querySelector(".nav-toggle");
  const navList = document.querySelector(".nav-list");

  if (toggle && navList) {
    toggle.addEventListener("click", () => {
      navList.classList.toggle("open");
    });
  }

  document.querySelectorAll(".has-dropdown > button.nav-link").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      if (window.innerWidth <= 720) {
        e.preventDefault();
        btn.parentElement.classList.toggle("open");
      }
    });
  });

  // Close dropdowns when a dropdown link is clicked (useful on mobile)
  document.querySelectorAll(".nav-list .dropdown a").forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".has-dropdown.open").forEach((li) => li.classList.remove("open"));
      const navListEl = document.querySelector(".nav-list");
      if (navListEl) navListEl.classList.remove("open");
    });
  });

  document.addEventListener("click", (e) => {
    const el = e.target.closest(".volume-toggle");
    if (!el) return;
    const body = el.nextElementSibling;
    const arrow = el.querySelector(".arrow");
    if (!body) return;
    const isHidden = body.style.display === "none";
    body.style.display = isHidden ? "block" : "none";
    if (arrow) arrow.textContent = isHidden ? "▾" : "▸";
  });

  /* ---------- Author Guidelines: sidebar TOC ---------- */
  const guidelinesNav = document.getElementById("guidelinesNav");

  if (guidelinesNav) {
    const HEADER_OFFSET = 130;

    const scrollToTarget = (id) => {
      const target = document.getElementById(id);
      if (!target) return;
      const top = target.getBoundingClientRect().top + window.pageYOffset - HEADER_OFFSET;
      window.scrollTo({ top, behavior: "smooth" });
    };

    // Expand/collapse a section without navigating
    guidelinesNav.querySelectorAll(".toc-arrow").forEach((arrow) => {
      arrow.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        arrow.closest(".toc-group, .toc-subgroup").classList.toggle("open");
      });
    });

    // Clicking a TOC entry jumps to the matching heading and expands its group
    guidelinesNav.querySelectorAll("a[href^='#']").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const id = link.getAttribute("href").slice(1);
        const group = link.closest(".toc-group, .toc-subgroup");
        if (group) group.classList.add("open");
        scrollToTarget(id);

        if (window.innerWidth <= 960) {
          guidelinesNav.classList.remove("mobile-open");
          const mobileToggle = document.querySelector(".sidebar-toggle-mobile");
          if (mobileToggle) mobileToggle.setAttribute("aria-expanded", "false");
        }
      });
    });

    // Mobile drawer toggle for the whole sidebar
    const mobileToggle = document.querySelector(".sidebar-toggle-mobile");
    if (mobileToggle) {
      mobileToggle.addEventListener("click", () => {
        const isOpen = guidelinesNav.classList.toggle("mobile-open");
        mobileToggle.setAttribute("aria-expanded", String(isOpen));
      });
    }

    // Highlight the TOC entry matching the section currently in view
    const sectionIds = Array.from(guidelinesNav.querySelectorAll("a[href^='#']")).map((a) =>
      a.getAttribute("href").slice(1)
    );
    const sections = sectionIds.map((id) => document.getElementById(id)).filter(Boolean);

    if (sections.length) {
      const linksById = {};
      guidelinesNav.querySelectorAll("a[href^='#']").forEach((a) => {
        linksById[a.getAttribute("href").slice(1)] = a;
      });

      const setActive = (id) => {
        guidelinesNav.querySelectorAll("a.active").forEach((a) => a.classList.remove("active"));
        const link = linksById[id];
        if (link) link.classList.add("active");
      };

      // Walk sections in document order and keep the last one whose heading
      // has already scrolled past the header offset — this is what was
      // marking the wrong (stale) TOC entry active when using
      // IntersectionObserver, since entries in a batch aren't guaranteed to
      // be processed in document order.
      let ticking = false;
      const updateActiveSection = () => {
        ticking = false;
        let currentId = sections[0].id;
        for (const section of sections) {
          if (section.getBoundingClientRect().top - HEADER_OFFSET <= 0) {
            currentId = section.id;
          } else {
            break;
          }
        }
        setActive(currentId);
      };

      window.addEventListener(
        "scroll",
        () => {
          if (!ticking) {
            ticking = true;
            requestAnimationFrame(updateActiveSection);
          }
        },
        { passive: true }
      );

      updateActiveSection();
    }
  }

  /* ---------- Contact the Editorial Office: form feedback ---------- */
  const contactForm = document.getElementById("contactForm");

  if (contactForm) {
    const successMsg = document.getElementById("formSuccess");

    contactForm.addEventListener("submit", (e) => {
      e.preventDefault();

      if (!contactForm.checkValidity()) {
        contactForm.reportValidity();
        return;
      }

      if (successMsg) successMsg.classList.add("visible");
      contactForm.reset();
    });
  }
});
