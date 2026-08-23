document.addEventListener('DOMContentLoaded',()=>{
 const form=document.querySelector('#calculator');
 if(form) form.addEventListener('submit',async e=>{e.preventDefault(); const q=new URLSearchParams(new FormData(form)); const r=await fetch('/api/calculate?'+q); const d=await r.json(); document.querySelector('#calc-result').innerHTML=`<span>CURRENT ATTENDANCE</span><h2>${d.percentage}%</h2><p>${d.prediction.message}</p><b class="badge ${d.status}">${d.status}</b>`});
 const chart=document.querySelector('#attendance-chart'); if(chart && window.Chart){new Chart(chart,{type:'bar',data:{labels:JSON.parse(chart.dataset.labels),datasets:[{label:'Attendance %',data:JSON.parse(chart.dataset.values),backgroundColor:'#7c72ff',borderRadius:12}]},options:{scales:{y:{beginAtZero:true,max:100,grid:{color:'rgba(100,110,150,.14)'}},x:{grid:{display:false}}},plugins:{legend:{display:false}}}})}
});
