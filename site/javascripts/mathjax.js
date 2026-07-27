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

document$.subscribe(({ body }) => {
  if (typeof MathJax !== "undefined" && MathJax.typesetPromise) {
    MathJax.typesetClear();
    MathJax.typesetPromise([body]);
  }
});
