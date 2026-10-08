/* Asumi T24 Console: page-scoped, safe read/write UI. No frontend data authority. */
(() => {
'use strict';
const page = document.body.dataset.page;
const root = document.getElementById('workspace');
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
const byId = id => document.getElementById(id);
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const asText = x => esc(x === null || x === undefined ? '—' : x);
const date = x => { try {return x ? new Date(x).toLocaleString('vi-VN') : '—';}catch {return String(x||'—');} };
const safeLink = x => {try{const u=new URL(x);return ['https:','http:'].includes(u.protocol)?u.href:'';}catch{return '';}};
const link = (url, label) => {const u=safeLink(url);return u ? '<a target="_blank" rel="noopener noreferrer" href="'+esc(u)+'">'+esc(label)+'</a>' : '—';};
const metric = (name, value, detail='') => '<article class="asumi-card"><div class="asumi-label">'+esc(name)+'</div><div class="asumi-metric">'+asText(value)+'</div><div class="asumi-caption">'+esc(detail)+'</div></article>';
const card = (title,content,extra='') => '<section class="asumi-card"><div class="asumi-section-head"><h2>'+esc(title)+'</h2>'+extra+'</div>'+content+'</section>';
const row = (title,subtitle='',right='')=>'<div class="asumi-item"><div><strong>'+asText(title)+'</strong><div class="asumi-caption">'+asText(subtitle)+'</div></div><div>'+right+'</div></div>';
const button=(label,action,id,cls='')=>'<button class="asumi-btn '+cls+'" data-action="'+esc(action)+'" data-id="'+esc(id??'')+'">'+esc(label)+'</button>';
const empty=message=>'<div class="asumi-empty">'+esc(message)+'</div>';
let busy=false;let lastResult=null;let cache={},offset=0,type='all',logFilter='all', activityQuery='';
function toast(message){const el=byId('asumi-toast');el.textContent=message;el.hidden=false;setTimeout(()=>{el.hidden=true},4000)}
function error(message){root.innerHTML='<div class="asumi-alert" role="alert">'+esc(message)+'</div>'+root.innerHTML}
async function api(path,opts={}){
 const o={credentials:'same-origin',...opts};
 if(o.method && !['GET','HEAD'].includes(o.method.toUpperCase()))o.headers={'Content-Type':'application/json','X-CSRF-Token':csrf,...(o.headers||{})};
 const r=await fetch(path,o);if(r.status===401){location.href='/login?next='+encodeURIComponent(location.pathname);throw Error('Đã hết phiên đăng nhập');}
 const j=await r.json();if(!r.ok||j.error||j.success===false)throw Error(j.error||('HTTP '+r.status));return j;
}
async function post(path,payload){return api(path,{method:'POST',body:JSON.stringify(payload||{})})}
function confirmDanger(question,word){if(!confirm(question))return false;return !word||prompt('Nhập '+word+' để xác nhận:')===word}
async function mutate(path,payload,question,word){if(question&&!confirmDanger(question,word))return;try{await post(path,payload);toast('Đã áp dụng thay đổi');await load()}catch(e){toast('Không thể thực hiện: '+e.message)}}
function statusHeader(s){
 const el=byId('top-status');el.textContent=s.bot_status==='Online'?'● Online':'● Offline';el.className='asumi-state '+(s.bot_status==='Online'?'good':'bad');
 byId('top-version').textContent='v'+(s.version||'—');
}
function stamp(){byId('last-updated').textContent='Cập nhật lúc '+new Date().toLocaleTimeString('vi-VN')}
async function overview(){
 const results=await Promise.allSettled([api('/api/stats'),api('/api/admin/feedback?limit=30'),api('/api/admin/feedback/metrics')]);
 const s=results[0].status==='fulfilled'?results[0].value:null;
 const t=results[1].status==='fulfilled'?(results[1].value.tickets||[]):[];
 const fm=results[2].status==='fulfilled'?results[2].value:null;
 if(s)statusHeader(s);
 const awaiting=t.filter(x=>['submitted','triage','needs_info','deferred','reopened'].includes(x.status));
 const errNote=results.some(x=>x.status==='rejected')?'<div class="asumi-alert">Một số nguồn dữ liệu chưa sẵn sàng. Thống kê còn thiếu được hiển thị bằng dấu —.</div>':'';
 const counters='<div class="asumi-grid">'+metric('Discord',s?.bot_status||'—','Trạng thái hiện tại')+metric('Feedback chờ xử lý',fm?.tickets_by_status?Object.entries(fm.tickets_by_status).filter(([k])=>['submitted','triage','needs_info','deferred','reopened'].includes(k)).reduce((sum,[,n])=>sum+Number(n||0),0):results[1].status==='fulfilled'?awaiting.length:'—','Số lượng cần xem xét')+metric('Latency',s?.latency||'—','Độ trễ Discord')+metric('Máy chủ',s?.guilds??'—','Đang tham gia')+'</div>';
 const tasks=awaiting.slice(0,6).map(x=>row(x.display_id+' · '+x.title,x.category+' · '+date(x.created_at),'<a class="asumi-btn asumi-btn-primary" href="/admin/feedback/'+encodeURIComponent(x.id)+'">Xem ticket</a>')).join('');
 const stats=s?'<div class="asumi-stack">'+row('Phiên hiện tại','Uptime '+(s.uptime||'—'),'RAM: '+esc(s.ram_usage||'—'))+row('Phiên bản',s.version||'—','<a href="/admin/releases">Changelog ↗</a>')+'</div>':empty('Không tải được trạng thái hệ thống.');
 root.innerHTML=errNote+counters+'<div class="asumi-cols">'+card('Cần xử lý',tasks||empty('Chưa có ticket cần xử lý.'),'<a href="/admin/feedback">Mở Inbox ↗</a>')+card('Sức khỏe hiện tại',stats,'<a href="/admin/monitoring">Logs ↗</a>')+'</div>';
}
function detailsContent(a){const obj={time:a.created_at||a.timestamp,type:a.action_type,action:a.action_name,status:a.status,duration_ms:a.duration_ms,model:a.model,user:a.user_name,guild:a.guild_name,details:a.details};return '<pre class="asumi-pre">'+esc(JSON.stringify(obj,null,2))+'</pre><details class="asumi-space-top"><summary>Nội dung ghi nhận (chỉ Admin)</summary><h3>Prompt</h3><pre class="asumi-pre">'+esc(a.prompt||'—')+'</pre><h3>Phản hồi</h3><pre class="asumi-pre">'+esc(a.response||'—')+'</pre></details>';}
function activityRows(items){return items.map(a=>'<tr><td>'+asText(date(a.timestamp||a.created_at||a.time))+'</td><td>'+asText(a.action_type)+'</td><td>'+asText(a.action_name)+'</td><td>'+asText(a.user_name)+'<div class="asumi-caption">'+asText(a.guild_name)+'</div></td><td>'+asText(a.status)+'</td><td>'+asText(a.duration_ms??a.execution_time_ms??'—')+'</td><td>'+button('Chi tiết','activity-detail',a.id)+'</td></tr>').join('');}
async function activity(){
 const path='/api/activities?limit=50&offset='+offset+'&type='+encodeURIComponent(type)+'&q='+encodeURIComponent(activityQuery);
 const d=await api(path);cache.activities=d.items||[];
 const select='<select class="asumi-input" id="type"><option value="all">Mọi tính năng</option>'+['assistant','summary','tarot','embed','command'].map(v=>'<option value="'+v+'" '+(type===v?'selected':'')+'>'+v+'</option>').join('')+'</select>';
 root.innerHTML=card('Nhật ký tương tác','<div class="asumi-panel-tools">'+select+'<input class="asumi-input" id="activity-q" placeholder="Tìm người dùng, server, lệnh..." value="'+esc(activityQuery)+'"><button class="asumi-btn" data-action="activity-search">Tìm</button></div><div class="asumi-table-wrap"><table class="asumi-table"><thead><tr><th>Thời gian</th><th>Loại</th><th>Thao tác</th><th>Người dùng</th><th>Kết quả</th><th>Thời gian (ms)</th><th></th></tr></thead><tbody>'+activityRows(cache.activities)+'</tbody></table></div>'+(!cache.activities.length?empty('Không có bản ghi phù hợp.'):'')+'<div class="asumi-panel-tools asumi-space-top"><button class="asumi-btn" data-action="activity-prev" '+(offset===0?'disabled':'')+'>← Trước</button><span class="asumi-progress">Bắt đầu từ '+(offset+1)+'</span><button class="asumi-btn" data-action="activity-next" '+(cache.activities.length<50?'disabled':'')+'>Tiếp →</button></div><div id="activity-detail"></div><div class="asumi-danger-zone">'+button('Xóa lịch sử tương tác','clear-activity','', 'asumi-btn-danger')+'</div>');
}
async function monitoring(){
 const s=await api('/api/stats');statusHeader(s);cache.logs=Array.isArray(s.logs)?s.logs:[];
 root.innerHTML='<div class="asumi-grid">'+metric('Discord',s.bot_status||'—')+metric('Uptime',s.uptime||'—')+metric('Latency',s.latency||'—')+metric('RAM',s.ram_usage||'—')+'</div>'+card('Console Logs','<div class="asumi-panel-tools"><select class="asumi-input" id="log-filter"><option value="all">Mọi cấp độ</option><option value="error">Lỗi</option><option value="warning">Cảnh báo</option></select><input id="log-search" class="asumi-input" placeholder="Lọc nội dung...">'+button('Lọc','log-filter','')+button('Sao chép logs','copy-logs','')+'</div><div id="log-body"></div><div class="asumi-danger-zone">'+button('Xóa logs','clear-logs','', 'asumi-btn-danger')+'</div>')+'<div class="asumi-space-top">'+card('Chẩn đoán kết nối','<p class="asumi-help">Trang hiển thị số liệu thực từ bot đang chạy. Turso, R2, Brave, Clef, Vectorize và MCP chỉ có trạng thái chi tiết khi backend cung cấp telemetry an toàn; không suy diễn trạng thái từ cấu hình hoặc mã nguồn.</p>')+'</div>';
 drawLogs();
}
function drawLogs(){const q=(byId('log-search')?.value||'').toLowerCase(),lvl=byId('log-filter')?.value||'all';const ls=(cache.logs||[]).map(x=>typeof x==='string'?x:JSON.stringify(x)).filter(x=>x.toLowerCase().includes(q)&& (lvl==='all'||(lvl==='error'?/error|traceback|exception|fatal/i:/warn|warning/i).test(x)));byId('log-body').innerHTML=ls.length?'<pre class="asumi-pre">'+esc(ls.join('\n'))+'</pre>':empty('Không có log phù hợp.');}
async function assistant(){
 const [stats,traces]=await Promise.allSettled([api('/api/stats'),api('/api/activities?type=assistant&limit=50')]);
 const s=stats.status==='fulfilled'?stats.value:null;const a=traces.status==='fulfilled'?(traces.value.items||[]):[];
 if(s)statusHeader(s);
 const allowed=['provider','route','tool','search_source','search_provider','fallback','fallback_reason','cache_status','latency_ms','vectorize_ms','clef_ms','history_hits','brave_calls'];
 const meta=x=>{const d=x.details&&typeof x.details==='object'?x.details:{};return allowed.filter(k=>d[k]!==undefined).map(k=>k+': '+String(d[k])).join(' · ')||'Không có telemetry định tuyến cho yêu cầu này';};
 root.innerHTML=card('Asumi AI & Search','<p class="asumi-help">Chỉ đọc metadata hoạt động đã lưu. Không tìm kiếm toàn bộ hội thoại Discord hay gửi dữ liệu riêng tư sang Brave.</p><div class="asumi-grid">'+metric('Summary model',s?.models?.summary||'—')+metric('AI model',s?.models?.data||'—')+metric('Search trạng thái','Chưa hỗ trợ','Backend chưa có health tổng hợp')+metric('Trace gần đây',traces.status==='fulfilled'?a.length:'—')+'</div>'+a.map(x=>row((x.action_name||x.action_type)+' · '+(x.status||'—'),meta(x),asText(date(x.timestamp||x.created_at)))).join('')+(!a.length?empty('Chưa có trace Asumi AI phù hợp.'):'')); 
}
async function tarot(){
 const [cr,rr]=await Promise.allSettled([api('/api/tarot/cooldowns'),api('/api/tarot/ratings/stats')]);
 const c=cr.status==='fulfilled'?(cr.value.cooldowns||[]):[],r=rr.status==='fulfilled'?rr.value:null;cache.cooldowns=c;
 const m='<div class="asumi-grid">'+metric('Daily cooldown',cr.status==='fulfilled'?c.length:'—')+metric('Đánh giá',r?.total??'—')+metric('Tích cực',r?.likes??'—')+metric('Hài lòng',r?.satisfaction_rate!==undefined?r.satisfaction_rate+'%':'—')+'</div>';
 root.innerHTML=m+card('Cooldown đang hoạt động','<div class="asumi-panel-tools"><input class="asumi-input" id="tarot-user" placeholder="Discord User ID"><button class="asumi-btn" data-action="tarot-reset-manual">Reset theo ID</button></div>'+c.map(x=>row(x.display_name||x.username||x.user_id,'#'+x.user_id+' · '+(x.card_title||'Daily'),button('Reset','tarot-reset',x.user_id))).join('')+(!c.length?empty('Không có user đang cooldown.'):'')+'<div class="asumi-panel-tools asumi-space-top"><a class="asumi-btn" href="/api/tarot/ratings/export?format=csv">Xuất Ratings CSV</a><a class="asumi-btn" href="/api/tarot/ratings/export?format=json">Xuất Ratings JSON</a></div><div class="asumi-danger-zone">'+button('Reset tất cả cooldown','tarot-reset-all','', 'asumi-btn-danger')+'</div>');
 if(cr.status==='rejected'||rr.status==='rejected')error('Một số dữ liệu Tarot chưa tải được.');
}
async function cabin(){
 const [ss,cc]=await Promise.allSettled([api('/api/cabin/sessions'),api('/api/cabin/shields')]);
 const sessions=ss.status==='fulfilled'?(ss.value.sessions||[]):[], shields=cc.status==='fulfilled'?(cc.value.shields||[]):[];
 root.innerHTML='<div class="asumi-grid">'+metric('Phiên trực tiếp',ss.status==='fulfilled'?sessions.length:'—')+metric('Khiên đang bật',cc.status==='fulfilled'?shields.length:'—')+'</div><div class="asumi-cols">'+card('Phiên đang chạy',sessions.map(s=>row(s.target_name||s.target_id,(s.guild_name||s.guild_id)+' · '+(s.remaining_str||'—'),button('Dừng phiên','cabin-stop',s.guild_id+':'+s.target_id,'asumi-btn-danger'))).join('')||empty('Không có phiên hoạt động.'))+card('Khiên miễn nhiễm','<div class="asumi-form"><label class="asumi-field">Guild ID<input id="shield-guild" class="asumi-input" inputmode="numeric"></label><label class="asumi-field">User ID<input id="shield-user" class="asumi-input" inputmode="numeric"></label>'+button('Thêm khiên','cabin-add','')+'</div>'+shields.map(s=>row(s.user_name||s.user_id,s.guild_name||s.guild_id,button('Gỡ','cabin-remove',s.guild_id+':'+s.user_id))).join('')+(!shields.length?empty('Chưa có khiên được bật.'):''))+'</div>';
 if(ss.status==='rejected'||cc.status==='rejected')error('Một số dữ liệu Cabin chưa tải được.');
}
async function guilds(){
 const d=await api('/api/guilds');cache.guilds=d.guilds||[];
 root.innerHTML=card('Máy chủ đang tham gia','<p class="asumi-help">'+asText(d.total)+' máy chủ. Thao tác Suspend và Leave sẽ ảnh hưởng trực tiếp đến bot.</p>'+cache.guilds.map(g=>row(g.name,'ID '+g.id+' · '+g.member_count+' thành viên · '+(g.is_suspended?'Đang tạm ngưng':'Hoạt động'),'<div class="asumi-actions">'+button(g.is_suspended?'Mở lại':'Tạm ngưng',g.is_suspended?'guild-unsuspend':'guild-suspend',g.id)+button('Rời máy chủ','guild-leave',g.id,'asumi-btn-danger')+'</div>')).join('')+(!cache.guilds.length?empty('Bot chưa tham gia máy chủ nào hoặc đang offline.'):''));
}
async function presence(){
 const d=await api('/api/presence');cache.presence=d;
 const options=(list,current)=>list.map(x=>'<option value="'+x+'" '+(String(current)===x?'selected':'')+'>'+x+'</option>').join('');
 root.innerHTML='<div class="asumi-cols">'+card('Chỉnh trạng thái Discord','<div class="asumi-form"><label class="asumi-field">Trạng thái<select id="presence-status" class="asumi-input">'+options(['online','idle','dnd','invisible'],d.status||'online')+'</select></label><label class="asumi-field">Hoạt động<select id="presence-type" class="asumi-input">'+options(['custom','playing','watching','listening','competing'],d.activity_type||'custom')+'</select></label><label class="asumi-field">Nội dung<input id="presence-text" class="asumi-input" maxlength="128" value="'+esc(d.activity_text||'')+'"></label><label class="asumi-flex"><input id="presence-rotating" type="checkbox" class="asumi-checkbox" '+(d.is_rotating?'checked':'')+'> Tự động xoay trạng thái</label>'+button('Lưu và áp dụng lên Discord','presence-save','', 'asumi-btn-primary')+'<div class="asumi-panel-tools"><button class="asumi-btn" data-action="presence-preset" data-id="live">Live</button><button class="asumi-btn" data-action="presence-preset" data-id="redeploy">Redeploy</button><button class="asumi-btn" data-action="presence-preset" data-id="bugfix">Bảo trì</button></div></div>')+card('Xem trước','<div class="asumi-metric">'+asText(d.activity_text||'Asumi')+'</div><p class="asumi-muted">Trạng thái hiện tại: '+asText(d.status)+' · Xoay tự động: '+(d.is_rotating?'Bật':'Tắt')+'</p><p class="asumi-help">Chỉ cập nhật khi bấm Lưu. Nếu Discord không nhận thay đổi, hệ thống sẽ báo lỗi.</p>')+'</div>';
}
async function releases(){
 const d=await api('/api/version');const info=d.info||{}, arr=d.changelog||[];
 root.innerHTML=card('Phiên bản hiện tại','<div class="asumi-metric">'+asText(info.version||info.current_version||'—')+'</div><p class="asumi-muted">'+asText(info.codename||'')+'</p>')+'<div class="asumi-space-top">'+card('Lịch sử phát hành',Array.isArray(arr)?arr.slice(0,30).map(v=>row(v.version||v.title||'Phiên bản',(v.date||v.release_date||'—')+' · '+(v.title||v.codename||''),asText(v.type||''))).join('')||empty('Không có thông tin phát hành.'):empty('Changelog chưa khả dụng.'))+'</div><div class="asumi-space-top">'+card('Kết nối ChatGPT / MCP','<p class="asumi-help">Phân quyền OAuth và token được quản lý trên server. Không hiển thị API secrets. Nếu muốn ngắt quyền ChatGPT, sử dụng thao tác thu hồi bên dưới.</p>'+button('Thu hồi các phiên kết nối MCP','mcp-revoke','', 'asumi-btn-danger'))+'</div>';
}
const loaders={overview,activity,monitoring,assistant,tarot,cabin,guilds,presence,releases};
async function load(){
 if(busy)return;busy=true;byId('refresh').disabled=true;
 // All pages show the actual Discord status, even those with specialized APIs.
 if(!['overview','monitoring','assistant'].includes(page)){
  api('/api/stats').then(statusHeader).catch(()=>{
    const status=byId('top-status');status.textContent='Trạng thái chưa xác định';status.className='asumi-state';
  });
 }
 try{await loaders[page]?.();stamp()}catch(e){root.innerHTML='<div class="asumi-alert" role="alert">Không tải được trang: '+esc(e.message)+'</div>'}finally{busy=false;byId('refresh').disabled=false}
}
document.addEventListener('click',async ev=>{
 const b=ev.target.closest('[data-action]');if(!b)return;
 const action=b.dataset.action,id=b.dataset.id;
 const actionPair=id.split(':');
 switch(action){
 case 'activity-detail':{const a=cache.activities?.find(x=>String(x.id)===id);if(a)byId('activity-detail').innerHTML=card('Chi tiết tương tác',detailsContent(a));break;}
 case 'activity-prev':offset=Math.max(0,offset-50);await load();break;
 case 'activity-next':offset+=50;await load();break;
 case 'activity-search':activityQuery=byId('activity-q').value.trim();type=byId('type').value;offset=0;await load();break;
 case 'log-filter':drawLogs();break;
 case 'copy-logs':try{await navigator.clipboard.writeText((cache.logs||[]).join('\\n'));toast('Đã sao chép logs')}catch(_){toast('Không thể sao chép logs')}break;
 case 'clear-logs':await mutate('/api/logs/clear',{},'Xóa toàn bộ console logs?','CLEAR');break;
 case 'clear-activity':await mutate('/api/activities/clear',{},'Xóa toàn bộ lịch sử tương tác?','CLEAR');break;
 case 'tarot-reset':await mutate('/api/tarot/reset-cooldown',{user_id:id},'Reset cooldown của user '+id+'?');break;
 case 'tarot-reset-manual':{const uid=byId('tarot-user').value.trim();if(!/^\d{5,20}$/.test(uid)){toast('User ID không hợp lệ');break;}await mutate('/api/tarot/reset-cooldown',{user_id:uid},'Reset cooldown của '+uid+'?');break;}
 case 'tarot-reset-all':await mutate('/api/tarot/reset-all-cooldowns',{},'Reset toàn bộ Tarot cooldown?', 'RESET');break;
 case 'cabin-stop':await mutate('/api/cabin/sessions/stop',{guild_id:actionPair[0],target_id:actionPair[1]},'Dừng phiên '+id+'?');break;
 case 'cabin-remove':await mutate('/api/cabin/shields/toggle',{guild_id:actionPair[0],user_id:actionPair[1],enable:false},'Gỡ khiên của '+id+'?');break;
 case 'cabin-add':{const g=byId('shield-guild').value.trim(),u=byId('shield-user').value.trim();if(!/^\d{5,20}$/.test(g)||!/^\d{5,20}$/.test(u)){toast('Guild ID/User ID không hợp lệ');break;}await mutate('/api/cabin/shields/toggle',{guild_id:g,user_id:u,enable:true},'Thêm khiên cho '+u+' ở '+g+'?');break;}
 case 'guild-suspend':await mutate('/api/guilds/suspend',{guild_id:id,reason:'Admin Console'},'Tạm ngưng bot tại máy chủ '+id+'?');break;
 case 'guild-unsuspend':await mutate('/api/guilds/unsuspend',{guild_id:id},'Mở hoạt động máy chủ '+id+'?');break;
 case 'guild-leave':{const g=cache.guilds?.find(x=>x.id===id);await mutate('/api/guilds/leave',{guild_id:id},'Bot sẽ rời '+(g?.name||id)+'. Không thể tự hoàn tác.','LEAVE');break;}
 case 'presence-preset':{const presets={live:['online','custom','',true],redeploy:['idle','playing','Đang cập nhật',false],bugfix:['dnd','custom','Đang bảo trì',false]};const p=presets[id];if(!p)break;byId('presence-status').value=p[0];byId('presence-type').value=p[1];byId('presence-text').value=p[2];byId('presence-rotating').checked=p[3];toast('Đã chọn preset — bấm Lưu để áp dụng');break;}
 case 'presence-save':await mutate('/api/presence',{status:byId('presence-status').value,activity_type:byId('presence-type').value,activity_text:byId('presence-text').value,is_rotating:byId('presence-rotating').checked});break;
 case 'mcp-revoke':await mutate('/api/admin/feedback/oauth/revoke',{},'Thu hồi tất cả kết nối MCP?','REVOKE');break;
 }
});
byId('refresh').addEventListener('click',load);
const mobile=byId('asumi-menu');const close=()=>{document.body.classList.remove('asumi-nav-open');mobile?.setAttribute('aria-expanded','false')};
mobile?.addEventListener('click',()=>{let opened=document.body.classList.toggle('asumi-nav-open');mobile.setAttribute('aria-expanded',String(opened))});
byId('asumi-overlay')?.addEventListener('click',close);
document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
load();
if(['overview','monitoring'].includes(page)){setInterval(()=>{if(!document.hidden&&!busy)load()},page==='monitoring'?30000:60000);}
})();
