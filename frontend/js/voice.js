// voice: Chrome Web Speech API
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;let rec=null;
$("#mic").onclick=()=>{if(!SR){$("#mic").title="Speech recognition needs Chrome";$("#mic").disabled=true;return}
  if(rec){rec.stop();return}rec=new SR();rec.lang=$("#lang").value;rec.interimResults=true;rec.continuous=true;const base=$("#inp").value;
  rec.onresult=e=>{NW.dictated=true;let t="";for(const r of e.results)t+=r[0].transcript;$("#inp").value=(base?base+" ":"")+t};
  rec.onend=()=>{rec=null;$("#mic").classList.remove("rec")};rec.onerror=()=>{};rec.start();$("#mic").classList.add("rec");};

