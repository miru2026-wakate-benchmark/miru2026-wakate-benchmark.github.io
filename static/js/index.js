(() => {
  "use strict";

  const papers = Array.isArray(window.PAPERS)
    ? window.PAPERS.map((paper, index) => ({ ...paper, sourceIndex: index }))
    : [];
  const pageSize = 16;
  let visibleCount = pageSize;
  let activeField = "すべて";

  const list = document.querySelector("#paper-list");
  const search = document.querySelector("#paper-search");
  const sort = document.querySelector("#paper-sort");
  const filters = document.querySelector("#field-filters");
  const count = document.querySelector("#result-count");
  const loadMore = document.querySelector("#load-more");
  const emptyState = document.querySelector("#empty-state");
  const clearFilters = document.querySelector("#clear-filters");
  const menuButton = document.querySelector(".menu-button");
  const nav = document.querySelector("#site-nav");

  document.querySelectorAll("[data-paper-count]").forEach((node) => {
    node.textContent = String(papers.length);
  });

  const normalize = (value) =>
    String(value || "")
      .normalize("NFKC")
      .toLocaleLowerCase("ja")
      .replace(/\s+/g, " ")
      .trim();

  const getYear = (value) => {
    const matched = String(value || "").match(/(?:19|20)\d{2}/);
    return matched ? Number(matched[0]) : 0;
  };

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const safeUrl = (value) => {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch {
      return "";
    }
  };

  function buildFilters() {
    const fields = ["すべて", ...new Set(papers.map((paper) => paper.field))];
    fields.forEach((field) => {
      const button = el("button", "filter-button", field);
      button.type = "button";
      button.dataset.field = field;
      button.classList.toggle("is-active", field === activeField);
      button.setAttribute("aria-pressed", String(field === activeField));
      button.addEventListener("click", () => {
        activeField = field;
        visibleCount = pageSize;
        filters.querySelectorAll("button").forEach((item) => {
          const selected = item.dataset.field === activeField;
          item.classList.toggle("is-active", selected);
          item.setAttribute("aria-pressed", String(selected));
        });
        render();
      });
      filters.append(button);
    });
  }

  function filteredPapers() {
    const query = normalize(search.value);
    const terms = query.split(" ").filter(Boolean);
    const result = papers.filter((paper) => {
      if (activeField !== "すべて" && paper.field !== activeField) return false;
      if (!terms.length) return true;
      const haystack = normalize(
        [
          paper.title,
          paper.authors,
          paper.venue,
          paper.year,
          paper.field,
          paper.motivation,
          paper.clarity,
          paper.summary,
        ].join(" "),
      );
      return terms.every((term) => haystack.includes(term));
    });

    if (sort.value === "newest") {
      result.sort((a, b) => getYear(b.year) - getYear(a.year) || a.sourceIndex - b.sourceIndex);
    } else if (sort.value === "oldest") {
      result.sort((a, b) => getYear(a.year) - getYear(b.year) || a.sourceIndex - b.sourceIndex);
    } else if (sort.value === "title") {
      result.sort((a, b) => a.title.localeCompare(b.title, "en"));
    } else {
      result.sort((a, b) => a.sourceIndex - b.sourceIndex);
    }
    return result;
  }

  function detailBlock(label, body, placeholder) {
    const block = el("div", "detail-block");
    block.append(el("span", "", label));
    block.append(el("p", body ? "" : "detail-placeholder", body || placeholder));
    return block;
  }

  function paperItem(paper, index) {
    const article = el("article", "paper-item");
    const number = el("div", "paper-number", String(index + 1).padStart(2, "0"));
    const main = el("div", "paper-main");
    const title = el("h3", "paper-title", paper.title);
    const authors = el("p", "paper-authors", paper.authors || "著者情報なし");
    main.append(title, authors);

    const meta = el("div", "paper-meta");
    meta.append(
      el("span", "", [paper.venue, paper.year].filter(Boolean).join(" · ") || "掲載情報なし"),
      el("span", "", paper.field),
    );
    const motivationClasses = {
      "領域開拓型": "palette-red",
      "欠落補完型": "palette-orange",
      "更新・難化型": "palette-green",
      "評価再設計型": "palette-blue",
    };
    if (paper.motivation) {
      meta.append(
        el(
          "span",
          `paper-motivation ${motivationClasses[paper.motivation] || ""}`.trim(),
          paper.motivation,
        ),
      );
    }

    const toggle = el("button", "paper-toggle", "+");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", `${paper.title} の詳細を表示`);

    const details = el("div", "paper-details");
    details.append(
      detailBlock("WHY IT MATTERS", paper.summary, "論文のポイントは整理中です。"),
      detailBlock("CLARITY NOTE", paper.clarity, "わかりやすさに関するコメントは整理中です。"),
    );
    const url = safeUrl(paper.url);
    if (url) {
      const link = el("a", "paper-external", "論文ページを開く ↗");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      details.lastElementChild.append(link);
    }

    toggle.addEventListener("click", () => {
      const open = article.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", `${paper.title} の詳細を${open ? "閉じる" : "表示"}`);
    });

    article.append(number, main, meta, toggle, details);
    return article;
  }

  function render() {
    const result = filteredPapers();
    const visible = result.slice(0, visibleCount);
    list.replaceChildren(...visible.map(paperItem));
    count.textContent = String(result.length);
    emptyState.hidden = result.length !== 0;
    loadMore.hidden = visibleCount >= result.length;
  }

  let searchTimer;
  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      visibleCount = pageSize;
      render();
    }, 100);
  });
  sort.addEventListener("change", () => {
    visibleCount = pageSize;
    render();
  });
  loadMore.addEventListener("click", () => {
    visibleCount += pageSize;
    render();
  });
  clearFilters.addEventListener("click", () => {
    search.value = "";
    sort.value = "source";
    activeField = "すべて";
    visibleCount = pageSize;
    filters.querySelectorAll("button").forEach((item) => {
      const selected = item.dataset.field === activeField;
      item.classList.toggle("is-active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    render();
  });

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      search.focus();
    }
  });

  menuButton.addEventListener("click", () => {
    const open = menuButton.getAttribute("aria-expanded") !== "true";
    menuButton.setAttribute("aria-expanded", String(open));
    nav.classList.toggle("is-open", open);
  });
  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      menuButton.setAttribute("aria-expanded", "false");
      nav.classList.remove("is-open");
    });
  });

  buildFilters();
  render();
})();
