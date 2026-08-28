/* Insert a contents block at the head of each article, in the manner of a
 * report's table of contents. Replaces the sticky "on this page" rail of the
 * three-column layout. Skipped on the front page and on pages with fewer
 * than two sections. */
document.addEventListener("DOMContentLoaded", function () {
  if (document.querySelector(".front-page")) return;
  var article = document.querySelector("article[role='main']");
  if (!article) return;
  var h1 = article.querySelector("h1");
  if (!h1) return;

  function anchorOf(heading) {
    var sec = heading.closest("section[id]");
    return sec ? "#" + sec.id : null;
  }

  function textOf(heading) {
    var clone = heading.cloneNode(true);
    clone.querySelectorAll("a.headerlink").forEach(function (a) {
      a.remove();
    });
    return clone.textContent.trim();
  }

  var items = [];
  article.querySelectorAll("h2").forEach(function (h2) {
    var href = anchorOf(h2);
    if (!href) return;
    var subs = [];
    h2.closest("section").querySelectorAll(":scope > section > h3").forEach(
      function (h3) {
        var sub = anchorOf(h3);
        if (sub) subs.push({ text: textOf(h3), href: sub });
      }
    );
    items.push({ text: textOf(h2), href: href, subs: subs });
  });
  if (items.length < 2) return;

  var nav = document.createElement("nav");
  nav.className = "page-contents";
  nav.setAttribute("aria-label", "Page contents");
  var title = document.createElement("p");
  title.className = "page-contents-title";
  title.textContent = "Contents";
  nav.appendChild(title);
  var ul = document.createElement("ul");
  items.forEach(function (item) {
    var li = document.createElement("li");
    var a = document.createElement("a");
    a.href = item.href;
    a.textContent = item.text;
    li.appendChild(a);
    if (item.subs.length) {
      var sub = document.createElement("ul");
      item.subs.forEach(function (s) {
        var sli = document.createElement("li");
        var sa = document.createElement("a");
        sa.href = s.href;
        sa.textContent = s.text;
        sli.appendChild(sa);
        sub.appendChild(sli);
      });
      li.appendChild(sub);
    }
    ul.appendChild(li);
  });
  nav.appendChild(ul);
  h1.parentNode.insertBefore(nav, h1.nextSibling);
});
