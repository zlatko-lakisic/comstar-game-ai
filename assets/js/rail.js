(function(){
  var nodes = Array.prototype.slice.call(document.querySelectorAll('.rail-node'));
  var sections = nodes.map(function(n){ return document.getElementById(n.dataset.target); });
  var fill = document.getElementById('railFill');
  var wrap = document.querySelector('.rail-track-wrap');
  if (!fill || !wrap || !nodes.length) return;

  function layoutNodes(){
    var h = wrap.clientHeight;
    var n = nodes.length;
    nodes.forEach(function(node, i){
      var pos = n > 1 ? (i / (n - 1)) : 0;
      node.style.top = (pos * h) + 'px';
    });
  }

  function setActive(idx){
    nodes.forEach(function(n, i){
      if (i === idx) n.classList.add('active');
      else n.classList.remove('active');
    });
  }

  function activeFromScroll(){
    var mid = window.innerHeight * 0.45;
    var best = 0;
    var bestDist = Infinity;
    sections.forEach(function(sec, i){
      if (!sec) return;
      var r = sec.getBoundingClientRect();
      // Prefer the section that contains the focus band; else nearest top.
      var dist;
      if (r.top <= mid && r.bottom >= mid) dist = 0;
      else dist = Math.abs(r.top - mid);
      if (dist < bestDist){
        bestDist = dist;
        best = i;
      }
    });
    setActive(best);
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
    activeFromScroll();
  }

  var ticking = false;
  function onScroll(){
    if (!ticking){
      window.requestAnimationFrame(function(){ updateProgress(); ticking = false; });
      ticking = true;
    }
  }

  window.addEventListener('resize', function(){ layoutNodes(); updateProgress(); });
  window.addEventListener('scroll', onScroll, { passive: true });
  layoutNodes();
  updateProgress();
})();
