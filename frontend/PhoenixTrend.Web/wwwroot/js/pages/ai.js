(() => {
  'use strict';
  const roots = ['portfolio','risk','settings','ai'];
  const mounted = new WeakSet();
  function enhance(host){
    if(!host || mounted.has(host)) return; mounted.add(host);
    const sync=()=>{
      host.querySelectorAll('.tabbar,.ai-modebar').forEach(bar=>{
        bar.setAttribute('role','tablist');
        bar.querySelectorAll('button').forEach(btn=>{
          btn.setAttribute('role','tab');
          btn.setAttribute('aria-selected',btn.classList.contains('active')?'true':'false');
        });
      });
    };
    host.querySelectorAll('.tabbar,.ai-modebar').forEach(bar=>{
      bar.addEventListener('wheel',e=>{ if(bar.scrollWidth>bar.clientWidth && Math.abs(e.deltaY)>Math.abs(e.deltaX)){bar.scrollLeft+=e.deltaY;e.preventDefault();}}, {passive:false});
    });
    const ro=new ResizeObserver(()=>{host.classList.toggle('pt-compact',host.clientWidth<1050);host.classList.toggle('pt-narrow',host.clientWidth<760)}); ro.observe(host);
    new MutationObserver(sync).observe(host,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
    sync();
  }
  function boot(){roots.forEach(n=>enhance(document.querySelector('.pt-'+n)));}
  new MutationObserver(boot).observe(document.getElementById('app')||document.body,{subtree:true,childList:true});
  document.readyState==='loading'?document.addEventListener('DOMContentLoaded',boot,{once:true}):boot();
})();
