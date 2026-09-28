
(function(){
 const seen=new WeakSet();
 function boot(){
   const page=document.querySelector(".pt-page");
   if(!page||seen.has(page)) return;
   seen.add(page);
   const cls=[...page.classList].find(x=>x.startsWith("pt-")&&x!=="pt-page");
   if(!cls)return;
   const name=cls.substring(3), fn=window["PhoenixPage_"+name];
   if(typeof fn==="function") requestAnimationFrame(fn);
 }
 new MutationObserver(boot).observe(document.documentElement,{subtree:true,childList:true});
 window.addEventListener("DOMContentLoaded",boot);
})();
