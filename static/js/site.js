// Шапка, просмотр фото, сетка альбома и выбор фото — общий скрипт всех страниц (вынесен из base.html 08.10.2026).
(function(){
  // ── Header scroll blur
  var hdr=document.querySelector('.js-header');
  window.addEventListener('scroll',function(){
    hdr.classList.toggle('scrolled',window.scrollY>10);
  },{passive:true});

  // ── Мобильное меню (гамбургер)
  var navToggle=document.querySelector('.js-nav-toggle');
  if(navToggle&&hdr){
    navToggle.addEventListener('click',function(){
      var open=hdr.classList.toggle('nav-open');
      navToggle.setAttribute('aria-expanded',open?'true':'false');
    });
    hdr.querySelectorAll('.menu a.link').forEach(function(a){
      a.addEventListener('click',function(){
        hdr.classList.remove('nav-open');
        navToggle.setAttribute('aria-expanded','false');
      });
    });
    // Аккордеон разделов в мобильном меню
    hdr.querySelectorAll('.js-acc-toggle').forEach(function(t){
      t.addEventListener('click',function(){
        var parent=t.closest('.menu-item');
        if(parent)parent.classList.toggle('open');
      });
    });
  }

  // ── Описание альбома (раскрытие по плюсику)
  document.querySelectorAll('.js-intro-toggle').forEach(function(t){
    t.addEventListener('click',function(){
      var d=t.closest('.album-intro');
      if(!d)return;
      var open=d.classList.toggle('open');
      t.setAttribute('aria-expanded',open?'true':'false');
      t.setAttribute('aria-label',open?'Свернуть описание':'Подробнее об альбоме');
    });
  });

  // ── Fade-in observer
  var fi=document.querySelectorAll('.fade-in');
  if(fi.length&&'IntersectionObserver' in window){
    var obs=new IntersectionObserver(function(entries){
      entries.forEach(function(e){if(e.isIntersecting){e.target.classList.add('visible');obs.unobserve(e.target)}});
    },{threshold:.12});
    fi.forEach(function(el){obs.observe(el)});
  }else{fi.forEach(function(el){el.classList.add('visible')})}

  // ── Lightbox
  var lb=document.getElementById('lightbox');
  var lbImg=document.getElementById('lb-img');
  var lbCnt=document.getElementById('lb-counter');
  var lbName=document.getElementById('lb-name');
  var lbDel=document.getElementById('lb-del');
  var lbAlbum=document.getElementById('lb-album');
  var photos=[],idx=0,currentItems=[],lbSelector='.photo-item',lbBound=false;
  var lbDelUrl=null,lbCsrf=null;

  function enterFs(el){var fn=el.requestFullscreen||el.webkitRequestFullscreen;if(fn){try{fn.call(el)}catch(e){}}}
  function exitFs(){var fsEl=document.fullscreenElement||document.webkitFullscreenElement;var fn=document.exitFullscreen||document.webkitExitFullscreen;if(fsEl&&fn){try{fn.call(document)}catch(e){}}}

  function openLb(i){
    idx=i;
    var p=photos[idx];
    if(!p)return;
    lbImg.src=p.src;
    lbImg.alt=p.alt||'';
    lbCnt.textContent=(idx+1)+' / '+photos.length;
    if(lbName){
      if(window.IS_STAFF&&p.alt){lbName.textContent=p.alt;lbName.style.display='block';}
      else{lbName.textContent='';lbName.style.display='none';}
    }
    if(lbDel)lbDel.style.display=(window.IS_STAFF&&lbDelUrl)?'block':'none';
    if(lbAlbum){if(p.album){lbAlbum.href=p.album;lbAlbum.style.display='block'}else{lbAlbum.style.display='none'}}
    var firstOpen=!lb.classList.contains('open');
    lb.classList.add('open');
    document.body.style.overflow='hidden';
    // полный экран — только с мышью или тачпадом (компьютер): на телефонах браузер при каждом
    // открытии показывает крупное уведомление (Роман, Fold 7, 02.10), а iPhone его сайтам не даёт
    if(firstOpen && window.matchMedia && matchMedia('(hover:hover) and (pointer:fine)').matches) enterFs(lb);
  }
  function closeLb(){lb.classList.remove('open');document.body.style.overflow='';exitFs();}
  function prevLb(){openLb((idx-1+photos.length)%photos.length)}
  function nextLb(){openLb((idx+1)%photos.length)}
  // Выход из полноэкранного режима (Esc) — закрыть просмотр
  function onFsChange(){var fsEl=document.fullscreenElement||document.webkitFullscreenElement;if(!fsEl&&lb.classList.contains('open'))closeLb();}
  document.addEventListener('fullscreenchange',onFsChange);
  document.addEventListener('webkitfullscreenchange',onFsChange);

  document.getElementById('lb-close').onclick=closeLb;
  document.getElementById('lb-prev').onclick=function(e){e.stopPropagation();prevLb()};
  document.getElementById('lb-next').onclick=function(e){e.stopPropagation();nextLb()};
  // тап/клик по самому фото — закрыть
  lbImg.addEventListener('click',function(e){e.stopPropagation();closeLb()});
  lb.addEventListener('click',function(e){if(e.target===lb)closeLb()});
  document.addEventListener('keydown',function(e){
    if(!lb.classList.contains('open'))return;
    if(e.key==='Escape')closeLb();
    if(e.key==='ArrowLeft')prevLb();
    if(e.key==='ArrowRight')nextLb();
  });

  // точечное удаление прямо в просмотре (для админа)
  if(lbDel){
    lbDel.addEventListener('click',function(e){
      e.stopPropagation();
      var p=photos[idx];
      if(!p||!lbDelUrl)return;
      if(!confirm('Отправить это фото в корзину? Его можно вернуть из «Корзины».'))return;
      var fd=new FormData();
      fd.append('ids',p.id);
      if(lbCsrf)fd.append('csrfmiddlewaretoken',lbCsrf);
      lbDel.disabled=true;
      fetch(lbDelUrl,{method:'POST',body:fd})
        .then(function(r){if(!r.ok)throw new Error();return r.json()})
        .then(function(d){
          lbDel.disabled=false;
          if(!d||!d.ok)throw new Error();
          if(p.el&&p.el.parentNode)p.el.parentNode.removeChild(p.el);
          rebuildPhotos();
          if(window.__galleryRefresh)window.__galleryRefresh();
          if(!photos.length){closeLb();return}
          openLb(idx>=photos.length?0:idx);
        })
        .catch(function(){lbDel.disabled=false;alert('Не удалось удалить. Проверьте, что вы вошли как админ.')});
    });
  }

  // swipe
  var tx=0;
  lb.addEventListener('touchstart',function(e){tx=e.touches[0].clientX},{passive:true});
  lb.addEventListener('touchend',function(e){
    var dx=e.changedTouches[0].clientX-tx;
    if(Math.abs(dx)>50){dx<0?nextLb():prevLb()}
  });

  function rebuildPhotos(){
    currentItems=Array.prototype.slice.call(document.querySelectorAll(lbSelector));
    photos=currentItems.map(function(el){
      var img=el.querySelector('img');
      return {src:el.dataset.full||(img&&img.src),alt:el.dataset.caption||(img&&img.alt)||'',id:el.dataset.id,album:el.dataset.album||'',el:el};
    });
    currentItems.forEach(function(el){el.style.cursor='zoom-in'});
  }
  window.__setLbDelete=function(url,token){lbDelUrl=url;lbCsrf=token};

  // init photo items (delegated click → no duplicate listeners on re-init)
  window.initLightbox=function(selector){
    lbSelector=selector||lbSelector;
    rebuildPhotos();
    if(!lbBound){
      document.addEventListener('click',function(e){
        var el=e.target.closest(lbSelector);
        if(!el)return;
        if(window.__selectMode)return;
        e.preventDefault();
        var i=currentItems.indexOf(el);
        if(i>=0)openLb(i);
      });
      lbBound=true;
    }
  };

  function mix(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}

  // Ленты барабанов из уже загруженных превью (к серверу запросов нет): у каждого барабана
  // свои картинки — одна и та же никогда не мелькает сразу в двух; подряд кадры не повторяются,
  // пока картинок хватает; сначала берутся те, что в прошлый раз не крутились (recent).
  // Возвращает по списку из n адресов на барабан.
  window.pickStrips=function(pool,exclude,recent,reels,n){
    var seen={},fresh=[],old=[];
    exclude.forEach(function(u){seen[u]=1});
    pool.forEach(function(u){if(u&&!seen[u]){seen[u]=1;(recent[u]?old:fresh).push(u)}});
    var cand=mix(fresh).concat(mix(old)), per=Math.min(n,Math.floor(cand.length/reels)), out=[];
    for(var r=0;r<reels;r++){
      var own=cand.slice(r*per,(r+1)*per), list=[];
      for(var k=0;k<n;k++)list.push(own.length?own[k%own.length]:'');  // любые per кадров подряд — разные
      out.push(list);
    }
    return out;
  };

  // ── Однорукий бандит: барабаны долго и плавно крутятся и по очереди останавливаются
  // на кадрах finals. Ленты — strips (по списку на барабан, см. pickStrips).
  window.spinReels=function(slot,finals,strips,done){
    var reels=[].slice.call(slot.querySelectorAll('.reel')), lever=slot.querySelector('.lever');
    if(lever){lever.classList.remove('pull');void lever.offsetWidth;lever.classList.add('pull')}
    var left=reels.length;
    reels.forEach(function(reel,k){
      var strip=reel.firstElementChild, H=reel.clientHeight, cur=reel.dataset.src||'', own=strips[k]||[];
      var urls=[cur];
      for(var n=0;n<25;n++)urls.push(own[n]||cur);
      var target=urls.length;
      urls.push(finals[k]||cur);
      urls.push(own[25]||cur);  // кадр под итоговым — виден, когда барабан чуть проскакивает
      strip.innerHTML='';
      urls.forEach(function(u){var i=document.createElement('img');i.src=u;i.alt='';strip.appendChild(i)});
      if(strip.getAnimations)strip.getAnimations().forEach(function(a){a.cancel()});
      strip.style.transition='filter .6s';strip.style.transform='translate3d(0,0,0)';
      function y(v){return 'translate3d(0,'+(-v)+'px,0)'}
      function stop(){reel.dataset.src=urls[target];if(--left===0&&done)done()}
      // где барабан замрёт, решает случай: чуть проскочит цель или чуть не докрутит
      // (на 12–22% окошка, у каждого барабана своё)
      var T=2.8+.7*k, off=Math.round(H*(.12+Math.random()*.1))*(Math.random()<.5?1:-1);
      var D=target*H+off, end=target*H;
      strip.classList.add('fast');
      setTimeout(function(){strip.classList.remove('fast')},T*550);
      if(!strip.animate){  // очень старый браузер: просто доехать до кадра
        void strip.offsetWidth;
        strip.style.transition='transform '+T+'s cubic-bezier(.15,.45,.33,1),filter .6s';
        strip.style.transform=y(end);
        setTimeout(stop,T*1000+50);
        return;
      }
      // Одно непрерывное движение, как у настоящего барабана:
      // 1) разгон с места за 0,3 с, пока опускается рычаг (дальше — меньше полкартинки за кадр, без мельтешения);
      // 2) долгое ровное торможение (скорость на стыке та же, без толчка);
      // 3) фиксатор ставит на ближайшую метку: проскочил — мягко откатывает назад, не докрутил — доворачивает.
      var tA=.3, tB=T-tA, tC=.5, total=T+tC, m=3;  // m — крутизна начала торможения (.45/.15)
      var dA=(m*D/tB)/(2/tA+m/tB);  // путь разгона, при котором скорость на стыке совпадает
      var anim=strip.animate([
        {transform:y(0),offset:0,easing:'cubic-bezier(.333,0,.667,.333)'},
        {transform:y(dA),offset:tA/total,easing:'cubic-bezier(.15,.45,.33,1)'},
        {transform:y(D),offset:T/total,easing:'cubic-bezier(.35,0,.25,1)'},
        {transform:y(end),offset:1}
      ],{duration:total*1000,fill:'forwards'});
      anim.onfinish=function(){strip.style.transform=y(end);anim.cancel();stop()};
    });
  };

  // ── Галерея: подгрузка порциями + выбор/удаление (для админа)
  window.initGallery=function(opts){
    opts=opts||{};
    var masonry=document.getElementById('masonry');
    if(!masonry)return;
    // Порция кадров. Адрес превью (src) в шаблонах есть только у первых 40, у остальных —
    // data-src: адрес ставится, когда до кадра дошла очередь. Иначе браузер разом просит у сервера
    // все превью (на «Барабане» 02.10 — 2429 запросов: сервер отказывал, кадры выходили битыми).
    var BATCH=40;
    var items=Array.prototype.slice.call(masonry.querySelectorAll('.photo-item'));
    var loadBtn=document.querySelector('.js-load-more');
    var loadWrap=document.querySelector('.load-more-wrap');
    var useIO=('IntersectionObserver' in window);
    var shown=BATCH;
    function applyShown(){
      items.forEach(function(el,i){
        el.classList.toggle('is-hidden',i>=shown);
        var img=i<shown&&el.querySelector('img');
        if(img&&!img.getAttribute('src')&&img.dataset.src)img.src=img.dataset.src;
      });
      if(loadBtn)loadBtn.style.display=(!useIO&&shown<items.length)?'inline-block':'none';
      scheduleLayout();
    }
    if(items.length>BATCH){applyShown()}else if(loadBtn){loadBtn.style.display='none'}
    if(loadBtn)loadBtn.addEventListener('click',function(){shown+=BATCH;applyShown()});

    // Автоподгрузка при прокрутке
    if(useIO&&loadWrap){
      var io=new IntersectionObserver(function(entries){
        if(entries[0].isIntersecting&&shown<items.length){
          shown+=BATCH;applyShown();
        }
      },{rootMargin:'400px'});
      io.observe(loadWrap);
    }

    // ── Выровненные ряды (justified), как у tankov: без дыр и без обрезки
    function ratioOf(el){
      var img=el.querySelector('img');
      if(el.dataset.ratio)return parseFloat(el.dataset.ratio);
      if(img&&img.naturalWidth&&img.naturalHeight){
        var r=img.naturalWidth/img.naturalHeight;el.dataset.ratio=r;return r;
      }
      return 0.72; // временно, пока фото не загрузилось
    }
    function layoutMasonry(){
      if(masonry.classList.contains('view-feed'))return;
      var cs=getComputedStyle(masonry);
      var padL=parseFloat(cs.paddingLeft)||0, padR=parseFloat(cs.paddingRight)||0,
          padT=parseFloat(cs.paddingTop)||0, padB=parseFloat(cs.paddingBottom)||0;
      var W=masonry.clientWidth-padL-padR;
      if(W<=0)return;
      var gap=window.innerWidth<=560?2:5;
      var target=window.innerWidth<=560?340:(window.innerWidth<=900?480:640);
      var vis=items.filter(function(el){return !el.classList.contains('is-hidden')});
      var row=[],ratios=[],sum=0,y=0;
      function place(stretch){
        if(!row.length)return;
        var avail=W-gap*(row.length-1);
        var h=stretch?(avail/sum):Math.min(target,avail/sum);
        h=Math.round(h);
        var x=0;
        row.forEach(function(el,j){
          var wpx=(stretch&&j===row.length-1)?(W-x):Math.round(ratios[j]*h);
          el.style.position='absolute';
          el.style.left=(padL+x)+'px';
          el.style.top=(padT+y)+'px';
          el.style.width=Math.max(1,wpx)+'px';
          el.style.height=h+'px';
          x+=wpx+gap;
        });
        y+=h+gap;
        row=[];ratios=[];sum=0;
      }
      vis.forEach(function(el){
        var r=ratioOf(el);
        row.push(el);ratios.push(r);sum+=r;
        if(sum*target+gap*(row.length-1)>=W)place(true);
      });
      place(false);
      masonry.style.height=(padT+(y>0?y-gap:0)+padB)+'px';
      masonry.classList.add('is-laid');
    }
    function clearMasonry(){
      items.forEach(function(el){
        el.style.position='';el.style.left='';el.style.top='';el.style.width='';el.style.height='';
      });
      masonry.style.height='';
    }
    var layoutTimer=null;
    function scheduleLayout(){clearTimeout(layoutTimer);layoutTimer=setTimeout(layoutMasonry,50);}
    // пересчёт по мере загрузки фото (узнаём настоящие пропорции);
    // не загрузилось (сервер занят) — ещё одна попытка через 1,5 с
    items.forEach(function(el){
      var img=el.querySelector('img');
      if(!img||(img.complete&&img.naturalWidth))return;
      img.addEventListener('load',function(){el.dataset.ratio='';ratioOf(el);scheduleLayout();});
      img.addEventListener('error',function(){
        var u=img.getAttribute('src');
        if(!u||img.dataset.retry)return;
        img.dataset.retry='1';
        setTimeout(function(){img.src=u+(u.indexOf('?')<0?'?':'&')+'r=1'},1500);
      });
    });
    window.addEventListener('resize',scheduleLayout);
    layoutMasonry();
    requestAnimationFrame(layoutMasonry);

    if(window.initLightbox)window.initLightbox('.photo-item');

    // дать лайтбоксу доступ к удалению (точечное удаление в просмотре)
    var _tokenEl=document.querySelector('[name=csrfmiddlewaretoken]');
    if(opts.deleteUrl&&window.IS_STAFF&&window.__setLbDelete){
      window.__setLbDelete(opts.deleteUrl,_tokenEl?_tokenEl.value:null);
    }
    // после удаления из просмотра — обновить внутренний список галереи
    window.__galleryRefresh=function(){
      items=Array.prototype.slice.call(masonry.querySelectorAll('.photo-item'));
      layoutMasonry();  // сразу закрыть место удалённого фото
    };
    if(opts.coverUrl){
      masonry.addEventListener('click',function(e){
        var star=e.target.closest('.cover-star');
        if(!star)return;
        e.preventDefault();e.stopImmediatePropagation();
        var item=star.closest('.photo-item');
        if(!item)return;
        var tokenEl=document.querySelector('[name=csrfmiddlewaretoken]');
        var fd=new FormData();
        fd.append('photo',item.dataset.id);
        if(tokenEl)fd.append('csrfmiddlewaretoken',tokenEl.value);
        fetch(opts.coverUrl,{method:'POST',body:fd})
          .then(function(r){if(!r.ok)throw new Error();return r.json()})
          .then(function(d){
            if(!d||!d.ok)throw new Error();
            masonry.querySelectorAll('.photo-item.is-cover').forEach(function(el){el.classList.remove('is-cover')});
            item.classList.add('is-cover');
            alert('Обложка назначена. Обновите главную, чтобы увидеть изменение.');
          })
          .catch(function(){alert('Не удалось назначить обложку. Проверьте, что вы вошли как админ.')});
      });
    }

    var selToggle=document.querySelector('.js-select-toggle');
    var delBtn=document.querySelector('.js-delete-selected');
    var moveCtl=document.querySelector('.js-move');
    if(selToggle&&delBtn){
      var selected={};
      function updateCount(){
        var n=Object.keys(selected).length;
        delBtn.textContent='Удалить выбранные ('+n+')';
        delBtn.style.display=n>0?'inline-block':'none';
        if(moveCtl)moveCtl.style.display=n>0&&opts.moveUrl?'inline-flex':'none';
      }
      selToggle.addEventListener('click',function(){
        var on=masonry.classList.toggle('select-mode');
        window.__selectMode=on;
        selToggle.textContent=on?'Готово':'Выбрать фото';
        if(!on){selected={};items.forEach(function(el){el.classList.remove('selected')});updateCount()}
      });
      masonry.addEventListener('click',function(e){
        if(!window.__selectMode)return;
        var el=e.target.closest('.photo-item');
        if(!el)return;
        e.preventDefault();e.stopPropagation();
        var id=el.dataset.id;
        if(selected[id]){delete selected[id];el.classList.remove('selected')}
        else{selected[id]=true;el.classList.add('selected')}
        updateCount();
      });
      delBtn.addEventListener('click',function(){
        var ids=Object.keys(selected);
        if(!ids.length)return;
        if(!confirm('Отправить выбранные фото ('+ids.length+') в корзину? Их можно вернуть из «Корзины».'))return;
        var tokenEl=document.querySelector('[name=csrfmiddlewaretoken]');
        var fd=new FormData();
        ids.forEach(function(id){fd.append('ids',id)});
        if(tokenEl)fd.append('csrfmiddlewaretoken',tokenEl.value);
        delBtn.disabled=true;
        fetch(opts.deleteUrl,{method:'POST',body:fd})
          .then(function(r){if(!r.ok)throw new Error('http');return r.json()})
          .then(function(d){
            if(!d||!d.ok){throw new Error('server')}
            ids.forEach(function(id){
              var el=masonry.querySelector('.photo-item[data-id="'+id+'"]');
              if(el)el.parentNode.removeChild(el);
            });
            selected={};updateCount();delBtn.disabled=false;
            items=Array.prototype.slice.call(masonry.querySelectorAll('.photo-item'));
            layoutMasonry();  // сразу закрыть места удалённых фото
            if(window.initLightbox)window.initLightbox('.photo-item');
            alert('В корзине: '+(d.deleted||ids.length)+'. Вернуть можно из «Корзины»; новые обложки — после обновления главной.');
          })
          .catch(function(){alert('Не удалось удалить. Проверьте, что вы вошли как админ, и попробуйте снова.');delBtn.disabled=false});
      });
      // перенести выбранные в другой альбом (страницы альбома и раздела)
      var moveBtn=moveCtl&&moveCtl.querySelector('.js-move-selected'), moveTo=moveCtl&&moveCtl.querySelector('.js-move-target');
      if(moveBtn&&moveTo&&opts.moveUrl){
        moveBtn.addEventListener('click',function(){
          var ids=Object.keys(selected);
          if(!ids.length)return;
          if(!moveTo.value){alert('Выберите альбом, куда перенести.');return}
          var label=moveTo.options[moveTo.selectedIndex].text;
          if(!confirm('Перенести выбранные фото ('+ids.length+') в «'+label+'»?'))return;
          var tokenEl=document.querySelector('[name=csrfmiddlewaretoken]');
          var fd=new FormData();
          ids.forEach(function(id){fd.append('ids',id)});
          fd.append('album',moveTo.value);
          if(tokenEl)fd.append('csrfmiddlewaretoken',tokenEl.value);
          moveBtn.disabled=true;
          fetch(opts.moveUrl,{method:'POST',body:fd})
            .then(function(r){return r.json().catch(function(){return {ok:false}})})
            .then(function(d){
              if(!d||!d.ok)throw new Error(d&&d.error||'');
              ids.forEach(function(id){
                var el=masonry.querySelector('.photo-item[data-id="'+id+'"]');
                if(el)el.parentNode.removeChild(el);
              });
              selected={};updateCount();moveBtn.disabled=false;moveTo.value='';
              items=Array.prototype.slice.call(masonry.querySelectorAll('.photo-item'));
              scheduleLayout();
              if(window.initLightbox)window.initLightbox('.photo-item');
              alert('Перенесено: '+d.moved+' в «'+d.album+'».');
            })
            .catch(function(err){alert('Не удалось перенести. '+(err.message||'Проверьте, что вы вошли как админ.'));moveBtn.disabled=false});
        });
      }
    }

    // «Вращайте барабан»: перемешать кадры прямо в браузере — к серверу запросов нет.
    // Следующий расклад готовится заранее, и его первые ряды (на первых трёх кадрах встанут
    // барабаны) загружаются, пока человек смотрит страницу, — барабан не останавливается
    // на пустом окошке, а загруженные кадры заодно идут на ленты барабанов.
    // По нажатию сетка гаснет и собирается заново, пока барабаны крутятся: первые кадры успевают
    // загрузиться и встать по своим пропорциям. Барабаны встали (window.__spinAnimate) —
    // готовая сетка проявляется.
    var spinBtn=document.querySelector('.js-spin');
    if(spinBtn){
      var next=null;
      var prepareNext=function(){
        var o=items.slice();
        for(var i=o.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1));var t=o[i];o[i]=o[j];o[j]=t;}
        o.slice(0,12).forEach(function(el){
          var img=el.querySelector('img');
          if(!img)return;
          img.loading='eager';
          if(!img.getAttribute('src')&&img.dataset.src)img.src=img.dataset.src;  // кадр скрыт — грузится без показа
        });
        next=o;
      };
      setTimeout(prepareNext,1500);  // после первых кадров страницы
      spinBtn.addEventListener('click',function(){
        if(spinBtn.dataset.busy)return;
        spinBtn.dataset.busy='1';
        if(!next)prepareNext();
        var order=next;
        next=null;
        masonry.classList.add('is-spinning');
        var built=false, loaded=null, revealed=false;
        function build(){
          if(built)return;
          built=true;
          items=order;
          items.forEach(function(el){masonry.appendChild(el)});
          // первые кадры грузим сразу, не дожидаясь прокрутки; проявляем, когда загрузятся первые ряды
          var first=items.slice(0,12).map(function(el){return el.querySelector('img')}).filter(Boolean);
          first.forEach(function(img){img.loading='eager'});
          shown=Math.min(BATCH,items.length);
          applyShown();
          items.slice(0,shown).forEach(function(el){el.classList.add('visible')});  // приехавшие наверх кадры — сразу видны
          if(window.initLightbox)window.initLightbox('.photo-item');
          loaded=Promise.all(first.slice(0,6).map(function(img){
            if(img.complete&&img.naturalWidth)return null;
            return new Promise(function(res){img.addEventListener('load',res,{once:true});img.addEventListener('error',res,{once:true})});
          }));
        }
        function reveal(){
          if(revealed)return;
          revealed=true;
          layoutMasonry();
          var top=masonry.getBoundingClientRect().top+window.scrollY-(window.innerWidth<=560?90:110);
          if(window.scrollY>top)window.scrollTo({top:Math.max(0,top),behavior:'smooth'});
          masonry.classList.add('is-revealing');
          masonry.classList.remove('is-spinning');
          setTimeout(function(){masonry.classList.remove('is-revealing')},750);
          delete spinBtn.dataset.busy;
          setTimeout(prepareNext,1000);  // и сразу готовим следующий расклад
        }
        function stopped(){
          build();
          loaded.then(reveal);
          setTimeout(reveal,1500);  // на медленной связи не ждать дольше полутора секунд
        }
        // собираем, когда барабаны уже закрутились (первый кадр показан) и сетка погасла
        requestAnimationFrame(function(){requestAnimationFrame(function(){setTimeout(build,500)})});
        if(window.__spinAnimate)window.__spinAnimate(order.slice(0,3),stopped);else setTimeout(stopped,700);
      });
    }

    // Переключатель вид: сетка / лента
    var gridBtn=document.querySelector('.js-view-grid');
    var feedBtn=document.querySelector('.js-view-feed');
    if(gridBtn&&feedBtn){
      function setView(feed){
        masonry.classList.toggle('view-feed',feed);
        gridBtn.classList.toggle('active',!feed);
        feedBtn.classList.toggle('active',feed);
        if(feed){clearMasonry();}else{layoutMasonry();}
      }
      gridBtn.addEventListener('click',function(){setView(false)});
      feedBtn.addEventListener('click',function(){setView(true)});
    }
  };
})();

// Клавиатура: фото, раскрытие меню и кнопки просмотра доступны Tab и открываются Enter/пробелом.
(function(){
  var SEL='.photo-item, .js-acc-toggle, .lightbox-close, .lightbox-arrow, .nav-toggle';
  function prepare(root){
    Array.prototype.forEach.call((root||document).querySelectorAll(SEL),function(el){
      if(el.tagName==='BUTTON'||el.tagName==='A')return;
      if(!el.hasAttribute('tabindex'))el.setAttribute('tabindex','0');
      if(!el.hasAttribute('role'))el.setAttribute('role','button');
      if(el.classList.contains('photo-item')&&!el.hasAttribute('aria-label'))
        el.setAttribute('aria-label','Открыть фото'+(el.dataset.caption?' «'+el.dataset.caption+'»':''));
    });
  }
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter'&&e.key!==' ')return;
    var el=e.target.closest&&e.target.closest(SEL);
    if(!el||el.tagName==='BUTTON'||el.tagName==='A'||e.target!==el)return;
    e.preventDefault();
    el.click();
  });
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){prepare()});
  else prepare();
})();
