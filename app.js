/**
 * Photopea AI Copilot - Web Interface & Live Bridge Client
 * Synchronizes Photopea with ChatGPT via MCP (Model Context Protocol).
 */

const state = {
  photopeaReady: false,
  activeDocument: {
    name: "Nessun documento",
    width: 0,
    height: 0,
    layers: []
  },
  actionCount: 0,
  currentCommandId: null
};

// DOM Elements
const dom = {
  iframe: document.getElementById('photopea-iframe'),
  statusPhotopea: document.getElementById('status-photopea'),
  statusMcp: document.getElementById('status-mcp'),
  btnUploadTrigger: document.getElementById('btn-upload-trigger'),
  inputPsdUpload: document.getElementById('input-psd-upload'),
  btnConvertImageTrigger: document.getElementById('btn-convert-image-trigger'),
  inputImageUpload: document.getElementById('input-image-upload'),
  btnConvertSampleAction: document.getElementById('btn-convert-sample-action'),
  btnSidebarUpload: document.getElementById('btn-sidebar-upload'),
  btnSidebarDemo: document.getElementById('btn-sidebar-demo'),
  btnExportPsdAction: document.getElementById('btn-export-psd-action'),
  dragDropOverlay: document.getElementById('drag-drop-overlay'),
  conversionModal: document.getElementById('conversion-modal'),
  conversionModalTitle: document.getElementById('conversion-modal-title'),
  conversionModalDesc: document.getElementById('conversion-modal-desc'),
  docActiveName: document.getElementById('doc-active-name'),
  docDimensionsTag: document.getElementById('doc-dimensions-tag'),
  docLayersCount: document.getElementById('doc-layers-count'),
  tabBtnLayers: document.getElementById('tab-btn-layers'),
  tabBtnActions: document.getElementById('tab-btn-actions'),
  panelLayers: document.getElementById('panel-layers'),
  panelActions: document.getElementById('panel-actions'),
  actionCountBadge: document.getElementById('action-count-badge'),
  copilotLayersList: document.getElementById('copilot-layers-list'),
  copilotFeedStream: document.getElementById('copilot-feed-stream'),
  btnForceRescan: document.getElementById('btn-force-rescan'),
  btnClearLog: document.getElementById('btn-clear-log'),
  copilotToast: document.getElementById('copilot-toast'),
  toastTitle: document.getElementById('toast-title'),
  toastDesc: document.getElementById('toast-desc'),
  inputCopilotPrompt: document.getElementById('input-copilot-prompt'),
  btnSendTesterPrompt: document.getElementById('btn-send-tester-prompt')
};

// ============================================================================
// UI Toast & Action Logger
// ============================================================================
function showCopilotToast(title, desc) {
  dom.toastTitle.textContent = title;
  dom.toastDesc.textContent = desc;
  dom.copilotToast.classList.add('show');
  setTimeout(() => {
    dom.copilotToast.classList.remove('show');
  }, 4000);
}

function appendActionToFeed(description, scriptSnippet, status = "Eseguito") {
  state.actionCount++;
  dom.actionCountBadge.textContent = state.actionCount;

  // Remove empty state message if first action
  const empty = dom.copilotFeedStream.querySelector('.empty-feed-msg');
  if (empty) empty.remove();

  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];

  const card = document.createElement('div');
  card.className = 'feed-item-card';
  card.innerHTML = `
    <div class="feed-item-header">
      <span class="feed-time">${timeStr}</span>
      <span class="feed-status-badge">✓ ${status}</span>
    </div>
    <div class="feed-desc">${description}</div>
    ${scriptSnippet ? `<div class="feed-code-snippet">${scriptSnippet.substring(0, 140)}...</div>` : ''}
  `;

  dom.copilotFeedStream.prepend(card);
}

// ============================================================================
// Layer Scanning & Rendering
// ============================================================================
const scanLayersScript = `
(function() {
  function scan(layers) {
    var res = [];
    for (var i = 0; i < layers.length; i++) {
      var l = layers[i];
      var item = {
        name: l.name,
        visible: l.visible,
        opacity: Math.round(l.opacity),
        kind: l.typename
      };
      try {
        if (l.bounds) {
          item.bounds = [
            Math.round(l.bounds[0].value),
            Math.round(l.bounds[1].value),
            Math.round(l.bounds[2].value),
            Math.round(l.bounds[3].value)
          ];
        }
      } catch(e) {}
      if (l.kind === LayerKind.TEXT) {
        item.type = "text";
        item.text = l.textItem.contents;
        try { item.fontSize = Math.round(l.textItem.size.value); } catch(e) {}
      } else if (l.kind === LayerKind.SMARTOBJECT) {
        item.type = "smartObject";
      } else {
        item.type = "pixel";
      }
      res.push(item);
    }
    return res;
  }

  try {
    var docW = 1080;
    var docH = 1080;
    try {
      docW = (typeof app.activeDocument.width === 'object' && app.activeDocument.width.value) ? app.activeDocument.width.value : Math.round(app.activeDocument.width);
      docH = (typeof app.activeDocument.height === 'object' && app.activeDocument.height.value) ? app.activeDocument.height.value : Math.round(app.activeDocument.height);
    } catch(e) {}

    var docData = {
      docName: app.activeDocument.name || "Documento",
      width: docW || 1080,
      height: docH || 1080,
      layers: scan(app.activeDocument.layers)
    };
    app.echoToOE("PP_LAYERS:" + JSON.stringify(docData));
  } catch(err) {
    app.echoToOE("PP_ERROR:" + err.toString());
  }
})();
`;

function renderLayersList(layers) {
  dom.copilotLayersList.innerHTML = '';
  if (!layers || layers.length === 0) {
    dom.copilotLayersList.innerHTML = '<div class="empty-layers-msg"><p>Nessun livello aperto. Carica un\'immagine o prova la demo.</p></div>';
    return;
  }

  layers.forEach((layer, idx) => {
    const card = document.createElement('div');
    card.className = 'copilot-layer-card';

    let roleTag = 'PIXEL';
    let roleClass = 'pill-pixel';
    let icon = '▢';

    if (layer.type === 'text') {
      roleTag = 'TEXT';
      roleClass = 'pill-text';
      icon = 'T';
    } else if (layer.type === 'smartObject') {
      roleTag = 'SMART OBJ';
      roleClass = 'pill-smart';
      icon = '✦';
    } else if (layer.name.toLowerCase().includes('background') || layer.name.toLowerCase().includes('sfondo')) {
      roleTag = 'BACKGROUND';
      roleClass = 'pill-bg';
    }

    let extraPreview = '';
    if (layer.text) {
      extraPreview = `
        <div class="layer-bottom-text" style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
          <span class="layer-text-preview" title="${layer.text}">"${layer.text}"</span>
          <button type="button" class="btn-micro edit-text-btn" data-name="${layer.name}" style="padding:2px 6px; font-size:0.65rem;" title="Modifica testo">✏️</button>
        </div>
      `;
    } else if (layer.bounds) {
      extraPreview = `<div class="layer-bottom-text">[${layer.bounds[0]}, ${layer.bounds[1]} - ${layer.bounds[2]}x${layer.bounds[3]}]</div>`;
    }

    const metaBadge = layer.fontSize ? `<span class="layer-meta-badge">${layer.fontSize}px</span>` : '';

    card.innerHTML = `
      <div class="layer-top-line">
        <div class="layer-tag-left">
          <span class="layer-kind-icon">${icon}</span>
          <span class="layer-title-text">${layer.name}</span>
          ${metaBadge}
        </div>
        <span class="layer-pill-role ${roleClass}">${roleTag}</span>
      </div>
      ${extraPreview}
    `;

    // Attach quick edit listener
    const editBtn = card.querySelector('.edit-text-btn');
    if (editBtn) {
      editBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const currentText = layer.text || '';
        const newText = prompt(`Modifica testo per il livello "${layer.name}":`, currentText);
        if (newText !== null && newText !== currentText) {
          const script = `
            for (var i = 0; i < app.activeDocument.layers.length; i++) {
              var l = app.activeDocument.layers[i];
              if (l.name === "${layer.name.replace(/"/g, '\\"')}") {
                l.textItem.contents = "${newText.replace(/"/g, '\\"')}";
                break;
              }
            }
          ` + "\n" + scanLayersScript;
          sendScriptToPhotopea(script);
          appendActionToFeed(`Modifica testo su "${layer.name}" → "${newText}"`, script.substring(0, 100));
          showCopilotToast('Livello Aggiornato', `Nuovo testo applicato a "${layer.name}".`);
        }
      });
    }

    dom.copilotLayersList.appendChild(card);
  });
}

function updateDocumentState(data) {
  state.activeDocument = data;
  dom.docActiveName.textContent = data.docName || "Documento Senza Titolo";
  dom.docDimensionsTag.textContent = `${data.width} x ${data.height} px`;
  dom.docLayersCount.textContent = `${data.layers.length} livelli rilevati`;
  renderLayersList(data.layers);

  // Sync with Server Bridge
  fetch('/api/bridge/layers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }).catch(() => {});
}

// ============================================================================
// Photopea WebMessaging Communication
// ============================================================================
function initPhotopea() {
  const config = {
    environment: {
      theme: 2,
      lang: "it",
      vmode: 0,
      intro: false,
      localsave: true,
      customIO: {
        save: "app.activeDocument.saveToOE('psd:true');"
      }
    }
  };

  const hashString = encodeURIComponent(JSON.stringify(config));
  dom.iframe.src = `https://www.photopea.com#${hashString}`;

  window.addEventListener('message', handlePhotopeaMessage);
}

function sendScriptToPhotopea(script) {
  if (!dom.iframe.contentWindow) return;
  dom.iframe.contentWindow.postMessage(script, "*");
}

function sendBinaryToPhotopea(arrayBuffer) {
  if (!dom.iframe.contentWindow) return;
  dom.iframe.contentWindow.postMessage(arrayBuffer, "*");
}

function handlePhotopeaMessage(event) {
  const data = event.data;

  // 1. Initial Handshake
  if (data === "done") {
    if (!state.photopeaReady) {
      state.photopeaReady = true;
      dom.statusPhotopea.querySelector('.status-label').textContent = 'Photopea Connesso';
      showCopilotToast('Photopea Connesso', 'Pronto a ricevere comandi da ChatGPT via MCP.');
    }
    return;
  }

  // 2. Custom JSON messages via app.echoToOE
  if (typeof data === 'string') {
    if (data.startsWith('PP_LAYERS:')) {
      try {
        const jsonStr = data.substring('PP_LAYERS:'.length);
        const parsed = JSON.parse(jsonStr);
        updateDocumentState(parsed);
      } catch (err) {}
    } else if (data.startsWith('PP_CMD_SUCCESS:')) {
      try {
        const jsonStr = data.substring('PP_CMD_SUCCESS:'.length);
        const parsed = JSON.parse(jsonStr);
        if (parsed.doc) {
          updateDocumentState(parsed.doc);
        }
        // Report success back to MCP server bridge
        if (state.currentCommandId) {
          fetch('/api/bridge/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: state.currentCommandId, success: true, details: parsed })
          }).catch(() => {});
          state.currentCommandId = null;
        }
      } catch(e) {}
    } else if (data.startsWith('PP_CMD_ERROR:')) {
      const errText = data.substring('PP_CMD_ERROR:'.length);
      console.error('[Photopea Error]:', errText);
      showCopilotToast('Errore Esecuzione', errText);
      if (state.currentCommandId) {
        fetch('/api/bridge/result', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: state.currentCommandId, success: false, error: errText })
        }).catch(() => {});
        state.currentCommandId = null;
      }
    }
    return;
  }

  // 3. Binary ArrayBuffer received (e.g. from saveToOE("psd:true") or "png")
  if (data instanceof ArrayBuffer) {
    const bytes = new Uint8Array(data.slice(0, 4));
    const isPsd = bytes[0] === 0x38 && bytes[1] === 0x42 && bytes[2] === 0x50 && bytes[3] === 0x53; // '8BPS'

    if (isPsd) {
      const blob = new Blob([data], { type: 'image/vnd.adobe.photoshop' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `photopea_copilot_${Date.now()}.psd`;
      a.click();
      showCopilotToast('File PSD Esportato', 'Il progetto Photoshop a livelli è stato salvato.');
    }
  }
}

// ============================================================================
// Real-Time Bridge Polling (Listens to ChatGPT MCP Commands)
// ============================================================================
let isPolling = false;

function startBridgePolling() {
  setInterval(async () => {
    if (isPolling) return;
    isPolling = true;

    try {
      const resp = await fetch('/api/bridge/pending');
      if (resp.ok) {
        const cmd = await resp.json();
        if (cmd && cmd.id && cmd.status === 'pending' && cmd.id !== state.currentCommandId) {
          state.currentCommandId = cmd.id;
          console.log('[Bridge] Nuovo comando da ChatGPT:', cmd);

          showCopilotToast('Istruzione da ChatGPT (MCP)', cmd.description || 'Modifica grafica in corso...');
          appendActionToFeed(cmd.description || 'Comando ExtendScript', cmd.script);

          // Execute script inside Photopea
          sendScriptToPhotopea(cmd.script);
        }
      }
    } catch(err) {
      // Bridge server offline or network blip
    } finally {
      isPolling = false;
    }
  }, 400);
}

// ============================================================================
// Demo Document Builder (Sample Multi-layer PSD created in Photopea)
// ============================================================================
function createDemoDocument() {
  const script = `
    var doc = app.documents.add(1080, 1080, 72, "Campagna_Social_AI", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
    
    // Background Base
    var bg = doc.artLayers.add();
    bg.name = "Background_Gradient";
    doc.selection.selectAll();
    var cBg = new SolidColor();
    cBg.rgb.red = 15; cBg.rgb.green = 20; cBg.rgb.blue = 30;
    doc.selection.fill(cBg);
    doc.selection.deselect();

    // Hero Visual Box
    var hero = doc.artLayers.add();
    hero.name = "Hero_Image_Box";
    doc.selection.select([[100, 360], [980, 360], [980, 780], [100, 780]]);
    var cHero = new SolidColor();
    cHero.rgb.red = 30; cHero.rgb.green = 40; cHero.rgb.blue = 60;
    doc.selection.fill(cHero);
    doc.selection.deselect();

    // Category Badge
    var badge = doc.artLayers.add();
    badge.name = "Badge_Categoria";
    badge.kind = LayerKind.TEXT;
    badge.textItem.contents = "INNOVAZIONE DIGITALE 2026";
    badge.textItem.size = 22;
    badge.textItem.position = [100, 150];
    var cCyan = new SolidColor();
    cCyan.rgb.red = 6; cCyan.rgb.green = 182; cCyan.rgb.blue = 212;
    badge.textItem.color = cCyan;

    // Headline Title
    var title = doc.artLayers.add();
    title.name = "Titolo_Principale";
    title.kind = LayerKind.TEXT;
    title.textItem.contents = "CREATIVITÀ AUTOMATIZZATA CON L'AI";
    title.textItem.size = 46;
    title.textItem.position = [100, 230];
    var cWhite = new SolidColor();
    cWhite.rgb.red = 248; cWhite.rgb.green = 250; cWhite.rgb.blue = 252;
    title.textItem.color = cWhite;

    // Subtitle
    var sub = doc.artLayers.add();
    sub.name = "Sottotitolo";
    sub.kind = LayerKind.TEXT;
    sub.textItem.contents = "Modifica file Photoshop in linguaggio naturale tramite ChatGPT e MCP.";
    sub.textItem.size = 24;
    sub.textItem.position = [100, 310];
    var cGray = new SolidColor();
    cGray.rgb.red = 148; cGray.rgb.green = 163; cGray.rgb.blue = 184;
    sub.textItem.color = cGray;

    // CTA Button
    var ctaBg = doc.artLayers.add();
    ctaBg.name = "Pulsante_CTA_Bg";
    doc.selection.select([[100, 860], [380, 860], [380, 930], [100, 930]]);
    var cIndigo = new SolidColor();
    cIndigo.rgb.red = 99; cIndigo.rgb.green = 102; cIndigo.rgb.blue = 241;
    doc.selection.fill(cIndigo);
    doc.selection.deselect();

    var cta = doc.artLayers.add();
    cta.name = "Testo_CTA";
    cta.kind = LayerKind.TEXT;
    cta.textItem.contents = "SCOPRI COME FARE →";
    cta.textItem.size = 20;
    cta.textItem.position = [130, 905];
    cta.textItem.color = cWhite;
  ` + "\n" + scanLayersScript;

  showCopilotToast('Documento Demo Creato', 'Inizializzato PSD multilivello in Photopea.');
  sendScriptToPhotopea(script);
}

// ============================================================================
// Event Listeners
// ============================================================================
function setupEventListeners() {
  // Tabs: Livelli vs Azioni
  dom.tabBtnLayers.addEventListener('click', () => {
    dom.tabBtnLayers.classList.add('active');
    dom.tabBtnActions.classList.remove('active');
    dom.panelLayers.classList.add('active');
    dom.panelActions.classList.remove('active');
  });

  dom.tabBtnActions.addEventListener('click', () => {
    dom.tabBtnActions.classList.add('active');
    dom.tabBtnLayers.classList.remove('active');
    dom.panelActions.classList.add('active');
    dom.panelLayers.classList.remove('active');
  });

  // Upload PSD
  dom.btnUploadTrigger.addEventListener('click', () => dom.inputPsdUpload.click());
  dom.inputPsdUpload.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    showCopilotToast('Caricamento PSD', `Apertura di ${file.name} in Photopea...`);
    const reader = new FileReader();
    reader.onload = (evt) => {
      sendBinaryToPhotopea(evt.target.result);
      setTimeout(() => {
        sendScriptToPhotopea(scanLayersScript);
      }, 1500);
    };
    reader.readAsArrayBuffer(file);

    // Also upload to server
    const formData = new FormData();
    formData.append('file', file);
    fetch('/api/upload-psd', { method: 'POST', body: formData }).catch(() => {});
  });

  // Image to PSD Converter Functions
  function setModalStep(id, status) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'step-item ' + (status || '');
  }

  async function convertImageFile(file) {
    if (!file) return;

    dom.conversionModal.classList.add('show');
    dom.conversionModalTitle.textContent = `Scomposizione di "${file.name}"...`;
    dom.conversionModalDesc.textContent = 'Analisi OCR ed inpainting sfondo in corso...';
    
    setModalStep('step-upload', 'active');
    setModalStep('step-ocr', '');
    setModalStep('step-inpaint', '');
    setModalStep('step-psd', '');

    const formData = new FormData();
    formData.append('file', file);

    try {
      setTimeout(() => {
        setModalStep('step-upload', 'done');
        setModalStep('step-ocr', 'active');
      }, 350);

      setTimeout(() => {
        setModalStep('step-ocr', 'done');
        setModalStep('step-inpaint', 'active');
      }, 950);

      const resp = await fetch('/api/convert-image', {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();

      if (data.status === 'success' && data.decomposition) {
        setModalStep('step-inpaint', 'done');
        setModalStep('step-psd', 'active');

        const decomp = data.decomposition;
        sendScriptToPhotopea(decomp.extendscript);

        setTimeout(() => {
          setModalStep('step-psd', 'done');
          sendScriptToPhotopea(scanLayersScript);
        }, 1100);

        setTimeout(() => {
          dom.conversionModal.classList.remove('show');
          showCopilotToast(
            'Immagine Scomposta!',
            `Creati ${decomp.detected_layers_count} livelli modificabili + sfondo pulito!`
          );
          appendActionToFeed(
            `Conversione immagine "${file.name}" in livelli PSD (${decomp.detected_layers_count} livelli testo)`,
            decomp.extendscript.substring(0, 140)
          );
        }, 1500);
      } else {
        throw new Error(data.message || 'Errore durante la conversione');
      }
    } catch (err) {
      dom.conversionModal.classList.remove('show');
      showCopilotToast('Errore Conversione', err.message);
    }
  }

  async function convertSampleDemo() {
    dom.conversionModal.classList.add('show');
    dom.conversionModalTitle.textContent = 'Scomposizione Immagine Demo (Social Post)...';
    dom.conversionModalDesc.textContent = 'Isolamento sfondo ed estrazione testi con OCR e Inpainting...';
    
    setModalStep('step-upload', 'done');
    setModalStep('step-ocr', 'active');
    setModalStep('step-inpaint', '');
    setModalStep('step-psd', '');

    try {
      setTimeout(() => {
        setModalStep('step-ocr', 'done');
        setModalStep('step-inpaint', 'active');
      }, 500);

      const resp = await fetch('/api/convert-sample', { method: 'POST' });
      const data = await resp.json();

      if (data.status === 'success' && data.decomposition) {
        setModalStep('step-inpaint', 'done');
        setModalStep('step-psd', 'active');

        const decomp = data.decomposition;
        sendScriptToPhotopea(decomp.extendscript);

        setTimeout(() => {
          setModalStep('step-psd', 'done');
          sendScriptToPhotopea(scanLayersScript);
        }, 1000);

        setTimeout(() => {
          dom.conversionModal.classList.remove('show');
          showCopilotToast(
            'Demo Convertita!',
            `Scomposta in ${decomp.detected_layers_count} livelli PSD modificabili in Photopea!`
          );
          appendActionToFeed(
            'Scomposizione immagine demo in livelli PSD modificabili',
            decomp.extendscript.substring(0, 140)
          );
        }, 1400);
      } else {
        throw new Error(data.message || 'Errore');
      }
    } catch (err) {
      dom.conversionModal.classList.remove('show');
      showCopilotToast('Errore', err.message);
    }
  }

  // Trigger Image Convert File Dialog
  if (dom.btnConvertImageTrigger) {
    dom.btnConvertImageTrigger.addEventListener('click', () => dom.inputImageUpload.click());
  }
  if (dom.btnSidebarUpload) {
    dom.btnSidebarUpload.addEventListener('click', () => dom.inputImageUpload.click());
  }
  if (dom.inputImageUpload) {
    dom.inputImageUpload.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) convertImageFile(file);
    });
  }

  // Trigger Sample Demo Conversion
  if (dom.btnConvertSampleAction) {
    dom.btnConvertSampleAction.addEventListener('click', convertSampleDemo);
  }
  if (dom.btnSidebarDemo) {
    dom.btnSidebarDemo.addEventListener('click', convertSampleDemo);
  }

  // Drag and Drop Handling on Window
  window.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (dom.dragDropOverlay) dom.dragDropOverlay.classList.add('active');
  });

  window.addEventListener('dragleave', (e) => {
    if (e.clientX <= 0 || e.clientY <= 0 || e.clientX >= window.innerWidth || e.clientY >= window.innerHeight) {
      if (dom.dragDropOverlay) dom.dragDropOverlay.classList.remove('active');
    }
  });

  window.addEventListener('drop', (e) => {
    e.preventDefault();
    if (dom.dragDropOverlay) dom.dragDropOverlay.classList.remove('active');
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.name.match(/\.(psd|psb)$/i)) {
        dom.inputPsdUpload.files = e.dataTransfer.files;
        dom.inputPsdUpload.dispatchEvent(new Event('change'));
      } else if (file.type.startsWith('image/') || file.name.match(/\.(png|jpe?g|webp|bmp)$/i)) {
        convertImageFile(file);
      }
    }
  });

  // Export PSD Action
  dom.btnExportPsdAction.addEventListener('click', () => {
    showCopilotToast('Esportazione...', 'Generazione del file PSD in corso da Photopea.');
    sendScriptToPhotopea('app.activeDocument.saveToOE("psd:true");');
  });

  // Force Rescan
  dom.btnForceRescan.addEventListener('click', () => {
    sendScriptToPhotopea(scanLayersScript);
  });

  // Clear Log
  dom.btnClearLog.addEventListener('click', () => {
    dom.copilotFeedStream.innerHTML = '<div class="empty-feed-msg"><p>Log pulito.</p></div>';
    state.actionCount = 0;
    dom.actionCountBadge.textContent = '0';
  });

  // Quick Direct Tester
  dom.btnSendTesterPrompt.addEventListener('click', () => {
    const prompt = dom.inputCopilotPrompt.value.trim();
    if (!prompt) return;

    fetch('/api/bridge/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        script: `
          if (app.activeDocument.artLayers.length > 0) {
            for (var i = 0; i < app.activeDocument.artLayers.length; i++) {
              var l = app.activeDocument.artLayers[i];
              if (l.kind === LayerKind.TEXT) {
                l.textItem.contents = "${prompt.replace(/"/g, '\\"')}";
                break;
              }
            }
          }
        `,
        description: `Istruzione AI: "${prompt}"`,
        timeout: 4.0
      })
    });
    dom.inputCopilotPrompt.value = '';
  });

  dom.inputCopilotPrompt.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') dom.btnSendTesterPrompt.click();
  });

  // Quick Chips
  document.querySelectorAll('.chip-item').forEach(chip => {
    chip.addEventListener('click', () => {
      const p = chip.getAttribute('data-prompt');
      dom.inputCopilotPrompt.value = p;
      dom.btnSendTesterPrompt.click();
    });
  });
}

// ============================================================================
// Startup
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  initPhotopea();
  startBridgePolling();
});
