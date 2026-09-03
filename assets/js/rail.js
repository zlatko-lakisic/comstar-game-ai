(function(){
  var nodes = Array.prototype.slice.call(document.querySelectorAll('.rail-node'));
  var sections = nodes.map(function(n){ return document.getElementById(n.dataset.target); });
  var fill = document.getElementById('railFill');
  var wrap = document.querySelector('.rail-track-wrap');
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function layoutNodes(){
    var h = wrap.clientHeight;
    var n = sections.length;
    nodes.forEach(function(node, i){
      var pos = n > 1 ? (i / (n - 1)) : 0;
      node.style.top = (pos * h) + 'px';
    });
  }

  function updateProgress(){
    var doc = document.documentElement;
    var scrollTop = window.scrollY || doc.scrollTop;
    var max = doc.scrollHeight - window.innerHeight;
    var p = max > 0 ? Math.min(1, Math.max(0, scrollTop / max)) : 0;
    if (window.innerWidth <= 900){
      fill.style.width = (p * 100) + '%';
      fill.style.height = '100%';
    } else {
      fill.style.height = (p * 100) + '%';
      fill.style.width = '100%';
    }
  }

  var ticking = false;
  function onScroll(){
    if (!ticking){
      window.requestAnimationFrame(function(){ updateProgress(); ticking = false; });
      ticking = true;
    }
  }

  var io = new IntersectionObserver(function(entries){
    entries.forEach(function(entry){
      var idx = sections.indexOf(entry.target);
      if (idx === -1) return;
      if (entry.isIntersecting){
        nodes.forEach(function(n){ n.classList.remove('active'); });
        nodes[idx].classList.add('active');
      }
    });
  }, { rootMargin: '-45% 0px -45% 0px', threshold: 0 });

  sections.forEach(function(s){ if (s) io.observe(s); });

  window.addEventListener('resize', layoutNodes);
  window.addEventListener('scroll', onScroll, { passive: true });
  layoutNodes();
  updateProgress();
})();
