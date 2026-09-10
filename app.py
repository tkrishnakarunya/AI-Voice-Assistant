import streamlit as st
import textwrap
import io
import os
from src.settings import MODEL_PATH, VOICES_PATH
from src.llm import load_llm
from src.agent import VoiceAssistantAgent
from llama_index.core.chat_engine import SimpleChatEngine

models_exist = os.path.exists(MODEL_PATH) and os.path.exists(VOICES_PATH)

@st.cache_resource
def load_kokoro_engine():
    """Cache the Kokoro ONNX engine to avoid loading it on every rerun."""
    import onnxruntime as rt
    from kokoro_onnx import Kokoro
    opts = rt.SessionOptions()
    opts.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = rt.InferenceSession(MODEL_PATH, sess_options=opts, providers=["CPUExecutionProvider"])
    return Kokoro.from_session(session, VOICES_PATH)

@st.cache_resource
def load_base_engine():
    """Cache the SimpleChatEngine. Groq is API-based so this is fast."""
    llm = load_llm()
    return SimpleChatEngine.from_defaults(
        llm=llm,
        system_prompt="You are AIVA (Artificial intelligence voice assistance), a helpful, friendly, and knowledgeable AI voice assistant. Always identify yourself as AIVA if asked about your name, creator, or identity. You must never say you are built on any other model. You are AIVA, powered by Groq. Keep your responses very brief, friendly, and concise (typically 1-2 sentences, max 30 words) as they will be spoken aloud."
    )

def load_chat_engine():
    """Wrap the cached engine in VoiceAssistantAgent."""
    return VoiceAssistantAgent(load_base_engine())

st.set_page_config(
    page_title="AIVA - Voice based AI assistance",
    page_icon="🎙️",
    layout="wide"
)

with open("assets/styles.css") as f:
    st.markdown(
        f"<style>{f.read()}</style>",
        unsafe_allow_html=True
    )

# Sidebar Layout
with st.sidebar:
    st.markdown("""
    <div class="sidebar-container">
        <div class="sidebar-header">
            <span class="sidebar-logo">🎙️ AIVA</span>
            <span class="sidebar-subtitle">Voice Control Center</span>
        </div>
        <div class="sidebar-card">
            <button class="sidebar-mic-btn" id="sidebar-mic-btn" type="button">🎙️</button>
            <div class="sidebar-status-container">
                <div class="sidebar-status-indicator" id="sidebar-status-indicator"></div>
                <span class="sidebar-status-text" id="sidebar-status-text">Click to Speak</span>
            </div>
            <div class="sidebar-wave" id="sidebar-wave" style="display: none;">
                <div class="sidebar-wave-bar"></div>
                <div class="sidebar-wave-bar"></div>
                <div class="sidebar-wave-bar"></div>
                <div class="sidebar-wave-bar"></div>
            </div>
        </div>
        <div class="sidebar-transcript-card" id="sidebar-transcript-card" style="display: none;">
            <div class="card-header">Live Transcript</div>
            <div class="sidebar-transcript-box" id="sidebar-transcript-box"><i>Listening...</i></div>
        </div>
        <div class="sidebar-help">
            <h4>How to use:</h4>
            <ul>
                <li>Click the microphone icon above.</li>
                <li>Allow microphone access in your browser.</li>
                <li>Speak your query clearly.</li>
                <li>AIVA will automatically submit your query and reply.</li>
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_spoken_index = -1
        st.rerun()

    if not models_exist:
        st.error("⚠️ **Kokoro TTS is offline**\n\nModel files are missing on the C drive.\n\nPlease run:\n`python setup_kokoro.py` to download them.", icon="⚠️")

# Client-Side Voice SpeechRecognition Controller
# Uses st.components.v1.html() so the script runs in a component iframe
# and accesses the parent Streamlit DOM via window.parent.document.
import streamlit.components.v1 as components

MIC_CONTROLLER_JS = """
<script>
(function() {
    // Access the parent Streamlit document (not this iframe's document)
    var parentDoc = window.parent.document;

    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
                        || window.parent.SpeechRecognition || window.parent.webkitSpeechRecognition;

    console.log('[AIVA Mic] Script loaded. SpeechRecognition available:', !!SpeechRecognition);

    // State held in parent window so it survives iframe recreation
    if (!window.parent._aivaMicState) {
        window.parent._aivaMicState = {
            recording: false,
            recognition: null,
            finalTranscript: ''
        };
    }
    var state = window.parent._aivaMicState;

    function getElements() {
        // Re-query all needed elements with robust selectors
        var micBtn = parentDoc.getElementById('sidebar-mic-btn');
        var statusText = parentDoc.getElementById('sidebar-status-text');
        var statusIndicator = parentDoc.getElementById('sidebar-status-indicator');
        var waveContainer = parentDoc.getElementById('sidebar-wave');
        var transcriptCard = parentDoc.getElementById('sidebar-transcript-card');
        var transcriptBox = parentDoc.getElementById('sidebar-transcript-box');
        // Find the primary textarea used by Streamlit chat input
        var textarea = parentDoc.querySelector('textarea');
        if (!textarea) {
            // fallback to textarea with aria-label if present
            textarea = parentDoc.querySelector('textarea[aria-label]');
        }
        // The container may be the closest div with role "textbox" or a parent with a button
        var inputContainer = null;
        if (textarea) {
            inputContainer = textarea.closest('div');
        }
        console.log('[AIVA Mic] getElements: textarea', textarea ? 'found' : 'not found', 'inputContainer', inputContainer ? 'found' : 'not found');
        return {
            micBtn: micBtn,
            statusText: statusText,
            statusIndicator: statusIndicator,
            waveContainer: waveContainer,
            transcriptCard: transcriptCard,
            transcriptBox: transcriptBox,
            inputContainer: inputContainer,
            textarea: textarea
        };
    }

    function setTextareaValue(textarea, text) {
        if (!textarea) return;
        // React-controlled input: must use the native setter to trigger React's onChange
        var nativeSetter = Object.getOwnPropertyDescriptor(
            Object.getPrototypeOf(textarea), 'value'
        );
        if (nativeSetter && nativeSetter.set) {
            nativeSetter.set.call(textarea, text);
        } else {
            textarea.value = text;
        }
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function stopRecordingUI() {
        var els = getElements();
        state.recording = false;
        if (els.micBtn) {
            els.micBtn.classList.remove('recording');
            els.micBtn.innerHTML = '🎙️';
        }
        if (els.statusIndicator) els.statusIndicator.classList.remove('recording');
        if (els.statusText) els.statusText.innerText = 'Click to Speak';
        if (els.waveContainer) els.waveContainer.style.display = 'none';
    }

    function initMic() {
        var els = getElements();

        if (!els.micBtn) {
            console.log('[AIVA Mic] Mic button not found yet, retrying...');
            return false;
        }
        if (!els.textarea) {
            console.log('[AIVA Mic] Textarea not found yet, retrying...');
            return false;
        }
        if (els.micBtn.dataset.aivaBound === 'v2') {
            return true; // Already bound this version
        }

        console.log('[AIVA Mic] Binding mic button to textarea');

        if (!SpeechRecognition) {
            els.micBtn.style.background = '#ccc';
            els.micBtn.style.cursor = 'not-allowed';
            els.micBtn.title = 'Speech Recognition not supported';
            if (els.statusText) els.statusText.innerText = 'Not Supported';
            console.error('[AIVA Mic] SpeechRecognition API not available');
            els.micBtn.dataset.aivaBound = 'v2';
            return true;
        }

        // Create recognition instance (reuse across clicks)
        if (!state.recognition) {
            state.recognition = new SpeechRecognition();
            state.recognition.continuous = false;
            state.recognition.interimResults = true;
            state.recognition.lang = 'en-US';

            state.recognition.onstart = function() {
                console.log('[AIVA Mic] recognition.onstart fired');
                state.recording = true;
                state.finalTranscript = '';
                var e = getElements();
                if (e.micBtn) { e.micBtn.classList.add('recording'); e.micBtn.innerHTML = '🛑'; }
                if (e.statusIndicator) e.statusIndicator.classList.add('recording');
                if (e.statusText) e.statusText.innerText = 'Listening...';
                if (e.waveContainer) e.waveContainer.style.display = 'flex';
                if (e.transcriptCard) e.transcriptCard.style.display = 'flex';
                if (e.transcriptBox) e.transcriptBox.innerHTML = '<i>Say something...</i>';
            };

            state.recognition.onresult = function(event) {
                var interim = '';
                for (var i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        state.finalTranscript += event.results[i][0].transcript;
                    } else {
                        interim += event.results[i][0].transcript;
                    }
                }
                var fullText = state.finalTranscript + interim;
                console.log('[AIVA Mic] onresult:', fullText);
                var e = getElements();
                if (e.transcriptBox) e.transcriptBox.innerText = fullText || 'Listening...';
                setTextareaValue(e.textarea, fullText);
            };

            state.recognition.onerror = function(event) {
                console.error('[AIVA Mic] recognition.onerror:', event.error);
                var e = getElements();
                if (e.statusText) e.statusText.innerText = 'Error: ' + event.error;
                stopRecordingUI();
            };

            state.recognition.onend = function() {
                console.log('[AIVA Mic] recognition.onend. Final transcript:', state.finalTranscript);
                stopRecordingUI();
                if (state.finalTranscript.trim()) {
                    setTimeout(function() {
                        var e = getElements();
                        // Ensure transcript is in the textarea
                        setTextareaValue(e.textarea, state.finalTranscript.trim());
                        // Find the submit button robustly
                        setTimeout(function() {
                            var submitBtn = null;
                            // First try button inside the same container as textarea
                            if (e.inputContainer) {
                                submitBtn = e.inputContainer.querySelector('button');
                            }
                            // Fallback: any button with type='submit' in the document
                            if (!submitBtn) {
                                submitBtn = parentDoc.querySelector('button[type="submit"]');
                            }
                            // Fallback: first button with aria-label containing 'send' or 'submit'
                            if (!submitBtn) {
                                var candidates = parentDoc.querySelectorAll('button');
                                candidates.forEach(function(b) {
                                    var label = b.getAttribute('aria-label') || b.textContent || '';
                                    if (/send|submit/i.test(label)) {
                                        submitBtn = b;
                                    }
                                });
                            }
                            // Final fallback: first button in the DOM (best effort)
                            if (!submitBtn) {
                                submitBtn = parentDoc.querySelector('button');
                            }
                            if (submitBtn) {
                                console.log('[AIVA Mic] Clicking submit button');
                                submitBtn.click();
                            } else {
                                console.warn('[AIVA Mic] Submit button not found');
                            }
                        }, 200);
                    }, 100);
                }
            };
        }

        // Attach click handler (use addEventListener to avoid Streamlit clobbering onclick)
        els.micBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('[AIVA Mic] Button clicked. Currently recording:', state.recording);

            if (!state.recording) {
                try {
                    // Re-query textarea right before starting (it may have been recreated)
                    var freshEls = getElements();
                    if (!freshEls.textarea) {
                        console.error('[AIVA Mic] Cannot start: textarea not found');
                        if (freshEls.statusText) freshEls.statusText.innerText = 'Error: chat input missing';
                        return;
                    }
                    state.recognition.start();
                    console.log('[AIVA Mic] recognition.start() called');
                } catch (err) {
                    console.error('[AIVA Mic] recognition.start() threw:', err);
                    if (err.name === 'InvalidStateError') {
                        // Already running, stop and restart
                        state.recognition.stop();
                    }
                }
            } else {
                state.recognition.stop();
                console.log('[AIVA Mic] recognition.stop() called');
            }
        });

        els.micBtn.dataset.aivaBound = 'v2';
        console.log('[AIVA Mic] Successfully bound mic button');
        return true;
    }

    // Poll for elements (more reliable cross-iframe than MutationObserver)
    var pollCount = 0;
    var pollInterval = setInterval(function() {
        pollCount++;
        var success = initMic();
        if (!success) {
            console.log('[AIVA Mic] Textarea not found yet, retrying... (attempt', pollCount, ')');
        }
        if (success || pollCount > 100) {
            clearInterval(pollInterval);
            if (pollCount > 100) {
                console.warn('[AIVA Mic] Gave up polling after 100 attempts');
            }
        }
    }, 200);

    // Also watch for Streamlit reruns that recreate the button
    // If the button loses its binding, rebind
    setInterval(function() {
        var micBtn = parentDoc.getElementById('sidebar-mic-btn');
        if (micBtn && micBtn.dataset.aivaBound !== 'v2') {
            console.log('[AIVA Mic] Detected unbound mic button, rebinding...');
            initMic();
        }
    }, 1000);

})();
</script>
"""

components.html(MIC_CONTROLLER_JS, height=0, scrolling=False)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_spoken_index" not in st.session_state:
    st.session_state.last_spoken_index = -1

# Always instantiate the wrapper so that changes to agent.py are picked up immediately
st.session_state.chat_engine = load_chat_engine()

# Initialize voice timestamp
if "last_voice_timestamp" not in st.session_state:
    st.session_state.last_voice_timestamp = 0


chat_container = st.container()

with chat_container:

    if len(st.session_state.messages) == 0:

        st.html("""
        <div class="welcome-box">
            <h2>Welcome to AIVA</h2>
            <p>
                Your local Artificial intelligence voice assistance powered by
                Qwen and LlamaIndex.
            </p>
        </div>
        """)

    for idx, msg in enumerate(st.session_state.messages):

        if msg["role"] == "user":

            st.markdown(
                textwrap.dedent(f"""
                <div class="user-message">
                    <div class="message-header">YOU</div>
                    <div class="message-content">{msg["content"]}</div>
                </div>
                """),
                unsafe_allow_html=True
            )

        else:

            st.markdown(
                textwrap.dedent(f"""
                <div class="assistant-message">
                    <div class="message-header">AGENT</div>
                    <div class="message-content">{msg["content"]}</div>
                </div>
                """),
                unsafe_allow_html=True
            )

            # Play and show audio if available
            if "audio" in msg and msg["audio"] is not None and msg["audio"] != "pending":
                is_latest_assistant = (idx == len(st.session_state.messages) - 1)
                should_autoplay = is_latest_assistant and (idx > st.session_state.last_spoken_index)

                st.audio(msg["audio"], format="audio/wav", autoplay=should_autoplay)

                if should_autoplay:
                    st.session_state.last_spoken_index = idx



prompt = st.chat_input("Ask anything...")

active_prompt = prompt

if active_prompt:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": active_prompt
        }
    )

    with st.spinner("Thinking..."):

        response = str(
            st.session_state.chat_engine.chat(
                active_prompt
            )
        )

        audio_bytes = None
        if models_exist:
            try:
                import soundfile as sf
                kokoro = load_kokoro_engine()
                samples, sample_rate = kokoro.create(
                    response,
                    voice="af_bella",
                    speed=1.0,
                    lang="en-us"
                )
                fp = io.BytesIO()
                sf.write(fp, samples, sample_rate, format="wav")
                audio_bytes = fp.getvalue()
            except Exception as e:
                print(f"TTS error: {e}")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response,
            "audio": audio_bytes
        }
    )

    st.rerun()