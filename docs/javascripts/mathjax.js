window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"], ["$", "$"]],
    displayMath: [["\\[", "\\]"], ["$$", "$$"]],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    ignoreHtmlClass: ".*",
    processHtmlClass: "arithmatex"
  }
};

document.addEventListener("DOMContentLoaded", function () {
  if (typeof MathJax !== "undefined" && MathJax.typesetPromise) {
    MathJax.typesetPromise();
  }
});

/* MkDocs Material Instant Navigation listener */
if (typeof location$ !== "undefined") {
  location$.subscribe(function () {
    if (typeof MathJax !== "undefined" && MathJax.typesetPromise) {
      MathJax.typesetClear();
      MathJax.typesetPromise();
    }
  });
}
