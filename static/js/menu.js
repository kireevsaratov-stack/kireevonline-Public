// Меню не влезает в строку (у админа пунктов больше, узкие окна, планшеты) — сворачиваем в гамбургер.
// Сразу после шапки, чтобы ничего не мелькнуло; ещё раз — когда загрузится шрифт и при смене размера окна.
(function(){
  var hdr=document.querySelector('.js-header');
  if(!hdr)return;
  function fitNav(){
    var was=hdr.classList.contains('nav-compact'), compact=false;
    hdr.classList.add('nav-measure');  // на время замера — без анимации меню
    hdr.classList.remove('nav-compact');
    if(window.innerWidth>760){
      var inner=hdr.querySelector('.inner'), logo=hdr.querySelector('.logo'), list=hdr.querySelector('.menu-list');
      var cs=getComputedStyle(inner);
      var free=inner.clientWidth-parseFloat(cs.paddingLeft)-parseFloat(cs.paddingRight)-logo.offsetWidth-24;
      compact=list.scrollWidth>free;
    }
    hdr.classList.toggle('nav-compact',compact);
    void hdr.offsetWidth;
    hdr.classList.remove('nav-measure');
    if(was!==compact)hdr.classList.remove('nav-open');
  }
  fitNav();
  var t;
  window.addEventListener('resize',function(){clearTimeout(t);t=setTimeout(fitNav,100)});
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fitNav);
})();
