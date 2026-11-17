// Vulcan Rotary - a six-barrel rotary gate / stutter for the MPC. Lumina Aerospace LLC.
//
// SPDX-License-Identifier: MIT
//
// THE IDEA
//   The M61 Vulcan is a six-barrel Gatling-type rotary cannon. The Gatling had fallen out of favour because it needs an
//   EXTERNAL POWER SOURCE to turn the barrels; jet fighters finally had electricity to spare. This effect is that gun
//   for audio: a rotor of six barrels turns, every barrel fires one shot (a pulse of your signal), and the barrels
//   spool up from rest and wind back down. What drives the motor is the "power source" (Mode):
//       Free   : the motor is always at full speed (a plain rotary gate).
//       Input  : your signal is the power supply. Audio above Threshold spools the barrels up; silence winds them down.
//       Fire   : the Fire switch is the trigger (automatable on the MPC: record it to play bursts).
//   RATE IS IN ROUNDS PER MINUTE, the gun's own unit (one shot = one round = one barrel step; six steps = one turn of the
//   rotor, so 6,000 rpm is 100 rounds a second and 1,000 rotor revolutions a minute). The "Gun" selector snaps Rate to the
//   historical figures: the 1949 T45 ground-fire at 2,500 rpm, the T45 at 4,000 rpm by 1950, the M61 at 6,000 rpm and the
//   1946 Project Vulcan contract's 7,200 rpm (the upper end of the Rate knob).
//
// SIGNAL PATH (per channel, stereo)
//   in -> Heat (soft saturation) -> Tone (SVF, cutoff stepped per barrel) -> rotary gate (Depth/Duty/Spread)
//      -> Scatter (each barrel sits at its own pan) -> + Report (a noise crack at every shot) -> Mix with dry -> Output
//      -> soft limiter.
//   The wet path is only engaged while the motor turns; at rest the audio passes through untouched.
//
// SHOT SHAPE: one pulse per barrel cycle, "Duty" long, shaped f(u) = s*(2-s), s = 4u(1-u): zero at both ends (no clicks),
//   squarer than a parabola. The six barrels fire in a fixed rotating order and fall a little short of each other by
//   fixed amounts (Spread), which is what makes it ratchet instead of buzz evenly.
//
// Hard rules honoured: parameter 0 is Output (harmless, host-nudged); no allocation/locks/IO in process();
// uid ("Lgyw") matches plugin.json; indices of existing parameters never change (append only).

#include "mpc_plugin.h"
#include "dsp/math.h"
#include "dsp/svf.h"
#include "dsp/smoother.h"
#include "dsp/tempo.h"
#include "dsp/noise.h"

#include <cmath>

using namespace mpc::dsp;

class VulcanRotary : public mpc::Plugin
{
public:
    enum Params
    {
        kOutput,                               // 0: master output (harmless on host nudge)
        kMix, kMode, kFire, kThreshold,
        kSync, kRate, kDiv, kSpinUp, kWindDown,
        kDepth, kDuty, kSpread, kScatter,
        kToneMode, kTone, kReso, kBarrelTone,
        kReport, kHeat,
        kGun,                                  // appended: snaps Rate to a historical gun
        kNumParams
    };

    VulcanRotary() : mpc::Plugin(makeInfo())
    {
        using namespace mpc;
        addParam(floatParam ("out",        "Output",      -24.0f, 12.0f, 0.0f, "dB", 1));
        addParam(floatParam ("mix",        "Mix",         0.0f, 100.0f, 100.0f, "%", 0));
        addParam(choiceParam("mode",       "Mode",        {"Free", "Input", "Fire"}, 0));
        addParam(boolParam  ("fire",       "Fire",        false));
        addParam(floatParam ("thresh",     "Threshold",   -60.0f, 0.0f, -30.0f, "dB", 0));
        addParam(boolParam  ("sync",       "Sync",        false));
        addParam(logParam   ("rate",       "Rate",        120.0f, 7200.0f, 3000.0f, "rpm", 0));
        addParam(choiceParam("div",        "Division",    divisionNames(), kDivisionSixteenth));
        addParam(floatParam ("spinup",     "Spin Up",     0.0f, 3000.0f, 400.0f, "ms", 0, 0.5f));
        addParam(floatParam ("winddown",   "Wind Down",   0.0f, 3000.0f, 600.0f, "ms", 0, 0.5f));
        addParam(floatParam ("depth",      "Depth",       0.0f, 100.0f, 100.0f, "%", 0));
        addParam(floatParam ("duty",       "Duty",        10.0f, 90.0f, 45.0f, "%", 0));
        addParam(floatParam ("spread",     "Spread",      0.0f, 100.0f, 35.0f, "%", 0));
        addParam(floatParam ("scatter",    "Scatter",     0.0f, 100.0f, 0.0f, "%", 0));
        addParam(choiceParam("tonemode",   "Tone Mode",   {"Off", "LP", "BP", "HP"}, 0));
        addParam(logParam   ("tone",       "Tone",        200.0f, 12000.0f, 3000.0f, "Hz", 0));
        addParam(floatParam ("reso",       "Reso",        0.0f, 100.0f, 25.0f, "%", 0));
        addParam(floatParam ("barreltone", "Barrel Tone", 0.0f, 100.0f, 0.0f, "%", 0));
        addParam(floatParam ("report",     "Report",      0.0f, 100.0f, 0.0f, "%", 0));
        addParam(floatParam ("heat",       "Heat",        0.0f, 100.0f, 0.0f, "%", 0));
        addParam(choiceParam("gun",        "Gun",         {"Manual", "T45 1949", "T45 1950", "M61", "Project Vulcan"}, 0));
        if (numParams() != kNumParams) mpc::log("Vulcan Rotary: parameter count mismatch (%d vs %d)", numParams(), (int)kNumParams);

        // Factory bank. Choice params take their index (Mode 0 Free 1 Input 2 Fire; Tone Mode 0 Off 1 LP 2 BP 3 HP;
        // Division indices: 3 = 1/16T, 4 = 1/16, 5 = 1/8T, 7 = 1/8; Gun 0 Manual 1 T45 1949 2 T45 1950 3 M61 4 Project Vulcan).
        auto program = [this](const char* name, std::initializer_list<std::pair<int, float>> o)
        {
            std::vector<float> v((size_t)numParams());
            for (int i = 0; i < numParams(); ++i) v[(size_t)i] = param(i).def;
            for (const auto& p : o) v[(size_t)p.first] = p.second;
            addProgram(name, std::move(v));
        };
        program("Init 50 Hz", {});
        program("M61 6000", {{kMode, 0}, {kGun, 3}, {kDepth, 100}, {kDuty, 40}, {kSpread, 45}, {kReport, 25}, {kHeat, 15}});
        program("Gun Run", {{kMode, 2}, {kFire, 1}, {kRate, 1320}, {kSpinUp, 1300}, {kWindDown, 900}, {kDepth, 100}, {kDuty, 42},
                            {kSpread, 60}, {kScatter, 40}, {kReport, 30}});
        program("Strafing Pass", {{kMode, 1}, {kThreshold, -35}, {kGun, 3}, {kSpinUp, 350}, {kWindDown, 900}, {kDepth, 90},
                                  {kSpread, 40}, {kScatter, 85}, {kToneMode, 2}, {kTone, 2500}, {kReso, 30}, {kBarrelTone, 40}, {kOutput, 6}});
        program("Hangar Stutter", {{kMode, 0}, {kSync, 1}, {kDiv, 4}, {kDepth, 100}, {kDuty, 50}, {kSpread, 0}});
        program("Triplet Roll", {{kMode, 0}, {kSync, 1}, {kDiv, 3}, {kDepth, 100}, {kDuty, 55}, {kSpread, 25}, {kScatter, 30}});
        program("Barrel Tone", {{kMode, 0}, {kRate, 840}, {kDepth, 55}, {kDuty, 70}, {kSpread, 20}, {kToneMode, 2}, {kTone, 1800},
                                {kReso, 60}, {kBarrelTone, 80}, {kOutput, 6}});
        program("Phantom Report", {{kMode, 0}, {kRate, 480}, {kDepth, 100}, {kDuty, 20}, {kSpread, 50}, {kReport, 80}, {kHeat, 60}});
        program("Wind Down", {{kMode, 2}, {kFire, 1}, {kRate, 2400}, {kSpinUp, 80}, {kWindDown, 2500}, {kDepth, 100}, {kDuty, 40},
                              {kToneMode, 1}, {kTone, 900}, {kReso, 40}});
        program("T45 1949", {{kMode, 0}, {kGun, 1}, {kDepth, 100}, {kDuty, 38}, {kSpread, 70}, {kReport, 55}, {kHeat, 35}});
        program("T45 1950", {{kMode, 0}, {kGun, 2}, {kDepth, 100}, {kDuty, 40}, {kSpread, 55}, {kReport, 40}, {kHeat, 25}});
        program("Project Vulcan 7200", {{kMode, 2}, {kFire, 1}, {kGun, 4}, {kSpinUp, 900}, {kWindDown, 1200}, {kDepth, 100}, {kDuty, 40},
                                        {kSpread, 40}, {kScatter, 55}, {kReport, 30}, {kHeat, 20}});
        program("Sidewinder", {{kMode, 0}, {kRate, 1800}, {kDepth, 70}, {kDuty, 35}, {kSpread, 30}, {kScatter, 100}});
    }

    void prepare(double sampleRate, int /*maxBlockSize*/) override
    {
        sr_ = (float)sampleRate; invSr_ = 1.0f / sr_;
        for (auto& f : tone_) f.setSampleRate(sampleRate);
        out_.setTime(10.0f, sampleRate); mix_.setTime(10.0f, sampleRate);
        envAtk_ = 1.0f - std::exp(-1.0f / (0.001f * sr_));
        envRel_ = 1.0f - std::exp(-1.0f / (0.060f * sr_));
        holdSamples_ = (int)(0.15f * sr_);
        reset();
    }

    void reset() override
    {
        for (auto& f : tone_) f.reset();
        spin_ = 0.0f; phase_ = 0.0f; barrel_ = 0; env_ = 0.0f; hold_ = 0; reportEnv_ = 0.0f; ctrl_ = 0;
        out_.snap(dbToGain(get(kOutput))); mix_.snap(get(kMix) * 0.01f);
    }

    void process(mpc::ProcessContext& ctx) override
    {
        readBlock(ctx);
        const float* inL = ctx.inputs[0];
        const float* inR = ctx.numInputs > 1 ? ctx.inputs[1] : ctx.inputs[0];
        float* outL = ctx.outputs[0];
        float* outR = ctx.numOutputs > 1 ? ctx.outputs[1] : ctx.outputs[0];
        const bool toneOn = b_.toneMode > 0;
        const float rateHz = b_.sync ? clamp(beatsToHz(divisionBeats(b_.div), ctx.transport.bpm), 0.5f, 150.0f) : b_.rate;

        for (int i = 0; i < ctx.numFrames; ++i)
        {
            const float dryL = inL[i], dryR = inR[i];   // read before writing: in and out are usually the same buffers

            // ----- the power source: what is turning the barrels? -----
            // The input envelope runs in every mode: Input mode is powered by it, and Report follows it.
            const float lvl = std::fmax(std::fabs(dryL), std::fabs(dryR));
            env_ += (lvl > env_ ? envAtk_ : envRel_) * (lvl - env_);
            bool powered;
            if (b_.mode == 0) powered = true;
            else if (b_.mode == 2) powered = b_.fire;
            else
            {
                if (env_ > b_.thresholdLin) hold_ = holdSamples_;
                else if (hold_ > 0) --hold_;
                powered = hold_ > 0;
            }
            if (b_.mode == 0) spin_ = 1.0f;
            else if (powered) { spin_ += b_.spinUpInc; if (spin_ > 1.0f) spin_ = 1.0f; }
            else              { spin_ -= b_.windDownInc; if (spin_ < 0.0f) spin_ = 0.0f; }
            const float engage = spin_ >= 0.1f ? 1.0f : spin_ * 10.0f;   // at rest the dry signal passes untouched

            float wetL = dryL, wetR = dryR;
            if (engage > 0.0f)
            {
                // ----- the rotor: barrels start nearly still and accelerate (ease-in) -----
                phase_ += rateHz * (0.05f + 0.95f * spin_ * spin_) * invSr_;
                if (phase_ >= 1.0f)
                {
                    phase_ -= 1.0f; barrel_ = barrel_ >= 5 ? 0 : barrel_ + 1;
                    reportEnv_ = 1.0f;                                          // a new shot: the muzzle report
                }
                const float u = phase_ * b_.invDuty;
                const float s = u < 1.0f ? 4.0f * u * (1.0f - u) : 0.0f;
                const float shot = s * (2.0f - s);
                const float barrelGain = 1.0f - b_.spread * kDip[barrel_];
                const float gate = 1.0f - b_.depth * (1.0f - shot * barrelGain);

                // ----- heat -> tone -> gate -> scatter -----
                if (b_.heat > 0.0f) { wetL = satur(wetL * b_.heatDrive) * b_.heatMakeup; wetR = satur(wetR * b_.heatDrive) * b_.heatMakeup; }
                if (toneOn)
                {
                    if ((ctrl_++ & 15) == 0)
                    {
                        const float fc = clamp(b_.tone * std::pow(2.0f, b_.barrelTone * kToneOct[barrel_]), 80.0f, 16000.0f);
                        tone_[0].set(fc, b_.reso); tone_[1].set(fc, b_.reso);
                    }
                    denorm_ = -denorm_;
                    wetL = tone_[0].process(wetL + denorm_, b_.toneSvfMode);
                    wetR = tone_[1].process(wetR + denorm_, b_.toneSvfMode);
                }
                const float g = gate * b_.makeup;
                wetL *= g * b_.panL[barrel_]; wetR *= g * b_.panR[barrel_];

                // ----- report: a crack of noise at each shot, decaying in ~4 ms -----
                if (b_.report > 0.0f && reportEnv_ > 0.001f)
                {
                    const float nL = noiseL_.process(), nR = noiseR_.process();
                    // the crack follows the signal (an idle insert must stay silent): full at -12 dBFS and above
                    const float follow = env_ * 4.0f > 1.0f ? 1.0f : env_ * 4.0f;
                    const float cr = reportEnv_ * b_.report * follow;
                    wetL += (nL - lastNL_) * cr; wetR += (nR - lastNR_) * cr;
                    lastNL_ = nL; lastNR_ = nR;
                    reportEnv_ *= b_.reportDecay;
                }
                // fade the wet path in with engage so spooling up from rest is click-free
                wetL = dryL + (wetL - dryL) * engage; wetR = dryR + (wetR - dryR) * engage;
            }

            const float mix = mix_.process(), og = out_.process();
            outL[i] = softLimit((dryL + (wetL - dryL) * mix) * og);
            outR[i] = softLimit((dryR + (wetR - dryR) * mix) * og);
        }
    }

private:
    static mpc::PluginInfo makeInfo()
    {
        mpc::PluginInfo i;
        i.name = "Vulcan Rotary";
        i.vendor = "Lumina Aerospace LLC";
        i.uniqueId = MPC_FOURCC('L', 'g', 'y', 'w');   // == plugin.json "uid"
        i.version = 1000;
        i.isInstrument = false;
        i.numInputs = 2;
        i.numOutputs = 2;
        i.tailSamples = 1;
        return i;
    }

    // how far each barrel's shot falls short at full Spread; and each barrel's cutoff offset (octaves) and pan position
    static constexpr float kDip[6]     = {0.00f, 0.18f, 0.07f, 0.30f, 0.12f, 0.40f};
    static constexpr float kToneOct[6] = {0.00f, 0.60f, -0.50f, 1.00f, -0.80f, 0.40f};
    static constexpr float kPan[6]     = {-0.90f, 0.50f, -0.30f, 0.90f, -0.60f, 0.20f};
    static constexpr float kShotMS     = 0.7111f;   // mean of f(u)^2 over one shot (numerically integrated)

    static float dbToGain(float dB) { return std::pow(10.0f, dB * 0.05f); }
    static float satur(float x) { x = clamp(x, -3.0f, 3.0f); return x * (27.0f + x * x) / (27.0f + 9.0f * x * x); }   // Pade tanh
    static float softLimit(float x)
    {
        const float a = x < 0.0f ? -x : x;
        if (a < 0.7f) return x;
        const float y = 0.7f + 0.3f * std::tanh((a - 0.7f) * (1.0f / 0.3f));
        return x < 0.0f ? -y : y;
    }

    struct Block
    {
        int mode = 0, div = 0, toneMode = 0, toneSvfMode = 0;
        bool fire = false, sync = false;
        float thresholdLin = 0.03f, rate = 50.0f, spinUpInc = 1.0f, windDownInc = 1.0f;
        float depth = 1.0f, invDuty = 2.0f, spread = 0.0f, tone = 3000.0f, reso = 0.25f, barrelTone = 0.0f;
        float report = 0.0f, reportDecay = 0.99f, heat = 0.0f, heatDrive = 1.0f, heatMakeup = 1.0f, makeup = 1.0f;
        float panL[6] = {1, 1, 1, 1, 1, 1}, panR[6] = {1, 1, 1, 1, 1, 1};
    } b_;

    void readBlock(mpc::ProcessContext& ctx)
    {
        b_.mode = getInt(kMode); b_.fire = getBool(kFire); b_.sync = getBool(kSync); b_.div = getInt(kDiv);
        b_.thresholdLin = dbToGain(get(kThreshold));
        // Rate is rounds per minute; the Gun selector overrides it with the historical cyclic rates (rpm)
        static const float kGunRpm[5] = {0.0f, 2500.0f, 4000.0f, 6000.0f, 7200.0f};
        const int gun = getInt(kGun);
        b_.rate = (gun > 0 && gun < 5 ? kGunRpm[gun] : get(kRate)) * (1.0f / 60.0f);   // -> shots per second
        const float up = get(kSpinUp), dn = get(kWindDown);
        b_.spinUpInc = up > 0.5f ? 1.0f / (up * 0.001f * sr_) : 1.0f;
        b_.windDownInc = dn > 0.5f ? 1.0f / (dn * 0.001f * sr_) : 1.0f;
        b_.depth = get(kDepth) * 0.01f;
        const float duty = get(kDuty) * 0.01f; b_.invDuty = 1.0f / duty;
        b_.spread = get(kSpread) * 0.01f;
        b_.toneMode = getInt(kToneMode); b_.toneSvfMode = b_.toneMode > 0 ? b_.toneMode - 1 : 0;   // LP 0, BP 1, HP 2
        b_.tone = get(kTone); b_.reso = get(kReso) * 0.01f; b_.barrelTone = get(kBarrelTone) * 0.01f;
        b_.report = get(kReport) * 0.01f * 0.6f; b_.reportDecay = std::exp(-1.0f / (0.004f * sr_));
        b_.heat = get(kHeat) * 0.01f; b_.heatDrive = 1.0f + b_.heat * 5.0f; b_.heatMakeup = 1.0f / std::sqrt(b_.heatDrive);
        // Level compensation: the gate throws away most of the signal; bring the RMS back toward the dry level.
        float bMS = 0.0f; for (int k = 0; k < 6; ++k) { const float g = 1.0f - b_.spread * kDip[k]; bMS += g * g; }
        bMS /= 6.0f;
        const float full = 1.0f / std::sqrt(std::fmax(0.05f, duty * kShotMS * bMS));
        b_.makeup = lerp(1.0f, std::fmin(full, 5.0f), b_.depth);
        const float sc = get(kScatter) * 0.01f;
        for (int k = 0; k < 6; ++k)
        {
            const float a = (kPan[k] * sc + 1.0f) * 0.7853982f;   // equal-power balance, 1.0 at centre
            b_.panL[k] = std::cos(a) * 1.4142136f; b_.panR[k] = std::sin(a) * 1.4142136f;
        }
        out_.setTarget(dbToGain(get(kOutput))); mix_.setTarget(get(kMix) * 0.01f);
        (void)ctx;
    }

    SVF tone_[2];
    Smoother out_, mix_;
    WhiteNoise noiseL_, noiseR_;
    float lastNL_ = 0.0f, lastNR_ = 0.0f;
    float sr_ = 44100.0f, invSr_ = 1.0f / 44100.0f, envAtk_ = 0.01f, envRel_ = 0.001f;
    float spin_ = 0.0f, phase_ = 0.0f, env_ = 0.0f, reportEnv_ = 0.0f, denorm_ = 1e-15f;
    int barrel_ = 0, hold_ = 0, holdSamples_ = 6615, ctrl_ = 0;
};

MPC_PLUGIN_ENTRY(VulcanRotary)
