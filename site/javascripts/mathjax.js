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
    if (MathJax.startup && MathJax.startup.promise) {
      MathJax.startup.promise
        .then(() => {
          MathJax.typesetClear([body]);
          return MathJax.typesetPromise([body]);
        })
        .catch((err) => console.error("MathJax typeset error:", err));
    } else {
      MathJax.typesetClear([body]);
      MathJax.typesetPromise([body]);
    }
  }
});
