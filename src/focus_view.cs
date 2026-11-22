// Focus Mode's pane, and the Workbench's: one WebView2 window, a child of HX Edit's main window, showing focus_view.html
// (or workbench.html, the page it is given).
// focus_view.py starts it and talks to it over its standard input and output:
//
//   FocusView.exe <parent window handle, 0 = its own window> <profile folder> <page url> <host=folder>...
//
//   in:  "P <json>"  posted to the page as it is (the catalog, the block's state)
//        "C <json>"  for the pane: {"visible":true,"x":..,"y":..,"w":..,"h":..} or {"close":true}
//   out: {"type":"ready"} once the page has loaded, {"type":"action","name":..,"value":..} for what
//        the page asks, {"type":"error","text":..}
//
// The page and its pictures are local folders served under the given host names. It can open nothing else.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

sealed class FocusView : Form
{
    [DllImport("user32.dll")] static extern IntPtr GetWindowDpiAwarenessContext(IntPtr hwnd);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int w, int h, uint flags);
    [DllImport("user32.dll")] static extern IntPtr SetFocus(IntPtr hwnd);
    [DllImport("user32.dll")] static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);

    // The page's undo, redo and save buttons: HX Edit's own Ctrl+Z, Ctrl+Shift+Z and Ctrl+S (its Edit and File menus' keys), typed into
    // HX Edit's window (the keyboard goes there first), so HX Edit undoes exactly as it does for the user. Nothing
    // for a pane with no HX Edit.
    void PressInEditor(byte key, bool shift)
    {
        if (parent == IntPtr.Zero || !IsWindow(parent)) return;
        SetFocus(parent);
        keybd_event(0x11, 0, 0, UIntPtr.Zero);          // Ctrl down
        if (shift) keybd_event(0x10, 0, 0, UIntPtr.Zero);
        keybd_event(key, 0, 0, UIntPtr.Zero);
        keybd_event(key, 0, 2, UIntPtr.Zero);           // key up
        if (shift) keybd_event(0x10, 0, 2, UIntPtr.Zero);
        keybd_event(0x11, 0, 2, UIntPtr.Zero);
    }

    readonly IntPtr parent;
    readonly string profile, page;
    readonly List<KeyValuePair<string, string>> hosts;
    readonly TextWriter output;
    readonly WebView2 view = new WebView2 { Dock = DockStyle.Fill };
    readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 };
    readonly Timer watch = new Timer { Interval = 250 };
    readonly List<string> waiting = new List<string>();   // messages for the page that came before it loaded
    Rectangle place, applied;
    bool wanted, loaded, started, closing;

    FocusView(IntPtr parent, string profile, string page, List<KeyValuePair<string, string>> hosts, TextWriter output)
    {
        this.parent = parent; this.profile = profile; this.page = page; this.hosts = hosts; this.output = output;
        FormBorderStyle = parent == IntPtr.Zero ? FormBorderStyle.Sizable : FormBorderStyle.None;
        if (parent != IntPtr.Zero) { TopLevel = false; ShowInTaskbar = false; }
        else { StartPosition = FormStartPosition.Manual; Bounds = new Rectangle(80, 80, 1600, 900); wanted = true; }
        AutoScaleMode = AutoScaleMode.None;
        Text = "Focus Mode · HX Edit Unbound";
        BackColor = Color.Black;
        view.DefaultBackgroundColor = Color.Black;
        Controls.Add(view);
        // HX Edit minimized, or gone: follow it.
        watch.Tick += (sender, args) => {
            if (parent == IntPtr.Zero || closing) return;
            if (!IsWindow(parent)) { Shutdown(); return; }
            Arrange();
        };
        FormClosing += (sender, args) => { closing = true; watch.Stop(); };
    }

    protected override CreateParams CreateParams
    {
        get
        {
            var settings = base.CreateParams;
            if (parent != IntPtr.Zero)
            {
                settings.Parent = parent;
                // WS_CHILD | WS_CLIPSIBLINGS | WS_CLIPCHILDREN, never a popup: it moves and hides with HX Edit.
                settings.Style = (settings.Style & ~unchecked((int)0x80000000) & ~0x10000000) | 0x40000000 | 0x04000000 | 0x02000000;
            }
            return settings;
        }
    }

    // A child pane starts hidden, and is shown only where and when the launcher says.
    protected override void SetVisibleCore(bool value)
    {
        base.SetVisibleCore(parent == IntPtr.Zero ? value : value && wanted);
    }

    void Arrange()
    {
        if (closing || IsDisposed || parent == IntPtr.Zero) return;
        bool show = wanted && place.Width > 60 && place.Height > 60 && !IsIconic(parent);
        if (show && place != applied)
        {
            // Above HX Edit's other child windows (the NAM tab), without taking the keyboard: SWP_NOACTIVATE.
            SetWindowPos(Handle, IntPtr.Zero, place.X, place.Y, place.Width, place.Height, 0x0010);
            applied = place;
        }
        if (Visible != show)
        {
            // Hidden, the pane must not keep the keyboard: HX Edit's own keys work again at once.
            if (!show && ContainsFocus) SetFocus(parent);
            Visible = show;
            Post("{\"type\":\"shown\",\"shown\":" + (show ? "true" : "false") + "}");
        }
        // Stay above HX Edit's other child windows (the NAM tab raises itself when it lays out):
        // SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE. The keyboard focus is never taken here.
        if (show) SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, 0x0013);
    }

    void Post(string message)
    {
        if (closing || IsDisposed) return;
        if (!loaded || view.CoreWebView2 == null) { if (waiting.Count < 64) waiting.Add(message); return; }
        try { view.CoreWebView2.PostWebMessageAsJson(message); }
        catch (Exception) { }   // a page that is reloading takes the next state
    }

    void Send(object value)
    {
        try { output.WriteLine(json.Serialize(value)); }
        catch (IOException) { }   // the launcher may already have gone
    }

    void Shutdown()
    {
        if (closing) return;
        closing = true; watch.Stop();
        try { Close(); } catch (Exception) { }
        // A pane whose window went with HX Edit's has nothing left to close: the process ends in any case.
        try { Application.ExitThread(); } catch (Exception) { }
        lastResort = new System.Threading.Timer(state => Environment.Exit(0), null, 1500, System.Threading.Timeout.Infinite);
    }
    System.Threading.Timer lastResort;

    // HX Edit gone (closed, or crashed) with this pane hidden: Windows destroys the child window with its parent, and
    // nothing on this thread may run again. A timer of its own ends the process then.
    static System.Threading.Timer orphanWatch;
    static void WatchParent(IntPtr parent)
    {
        if (parent == IntPtr.Zero) return;
        orphanWatch = new System.Threading.Timer(state => { if (!IsWindow(parent)) Environment.Exit(0); }, null, 2000, 2000);
    }

    bool OnUi(Action action)
    {
        if (closing || IsDisposed || !IsHandleCreated) return false;
        try { BeginInvoke(action); return true; }
        catch (InvalidOperationException) { return false; }
    }

    void Control(string text)
    {
        Dictionary<string, object> message;
        try { message = json.Deserialize<Dictionary<string, object>>(text); }
        catch (Exception) { return; }
        if (message == null) return;
        object value;
        if (message.TryGetValue("close", out value) && value is bool && (bool)value) { Shutdown(); return; }
        wanted = message.TryGetValue("visible", out value) && value is bool && (bool)value;
        try
        {
            if (message.ContainsKey("x"))
                place = new Rectangle(Convert.ToInt32(message["x"]), Convert.ToInt32(message["y"]),
                                      Convert.ToInt32(message["w"]), Convert.ToInt32(message["h"]));
        }
        catch (Exception) { }
        Arrange();
    }

    void ReadCommands(TextReader input)
    {
        try
        {
            for (string line; (line = input.ReadLine()) != null;)
            {
                if (line.Length < 3 || line[1] != ' ') continue;
                var kind = line[0]; var body = line.Substring(2);
                if (!OnUi(() => { if (kind == 'P') Post(body); else if (kind == 'C') Control(body); })) return;
            }
        }
        catch (IOException) { }
        catch (ObjectDisposedException) { }
        if (!OnUi(Shutdown)) Environment.Exit(0);   // the launcher closed its end: nothing left to show
    }

    async Task Start(TextReader input)
    {
        if (started) return;
        started = true;
        try
        {
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: profile);
            if (closing || IsDisposed) return;
            await view.EnsureCoreWebView2Async(environment);
            if (closing || IsDisposed) return;
            var core = view.CoreWebView2;
            core.Profile.PreferredColorScheme = CoreWebView2PreferredColorScheme.Dark;
            core.Settings.AreHostObjectsAllowed = false;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.IsZoomControlEnabled = false;
            core.Settings.AreBrowserAcceleratorKeysEnabled = false;
            core.Settings.IsWebMessageEnabled = true;
            foreach (var host in hosts)
                core.SetVirtualHostNameToFolderMapping(host.Key, host.Value, CoreWebView2HostResourceAccessKind.Allow);
            // Only the local page: no other address, no new window, no download, no external program.
            core.NavigationStarting += (sender, args) => args.Cancel = args.Uri != page;
            core.NewWindowRequested += (sender, args) => args.Handled = true;
            core.DownloadStarting += (sender, args) => args.Cancel = true;
            core.LaunchingExternalUriScheme += (sender, args) => args.Cancel = true;
            core.DOMContentLoaded += (sender, args) => {
                loaded = true;
                foreach (var message in waiting) Post(message);
                waiting.Clear();
                Send(new { type = "ready" });
            };
            core.WebMessageReceived += (sender, args) => {
                if (args.Source != page) return;
                string text;
                try { text = args.TryGetWebMessageAsString(); }
                catch (Exception) { return; }
                if (String.IsNullOrEmpty(text) || text.Length > 4096) return;
                Dictionary<string, object> message;
                try { message = json.Deserialize<Dictionary<string, object>>(text); }
                catch (Exception) { return; }
                object name, value;
                if (message == null || !message.TryGetValue("name", out name) || !(name is string)) return;
                message.TryGetValue("value", out value);
                if ((string)name == "undo") { PressInEditor(0x5A, false); return; }      // Ctrl+Z
                if ((string)name == "redo") { PressInEditor(0x5A, true); return; }       // Ctrl+Shift+Z
                if ((string)name == "save") { PressInEditor(0x53, false); return; }      // Ctrl+S: HX Edit's File > Save Preset
                Send(new { type = "action", name = (string)name, value = value });
            };
            core.Navigate(page);
            watch.Start();
            Arrange();
            await Task.Run(() => ReadCommands(input));
        }
        catch (Exception error)
        {
            if (closing || IsDisposed) return;
            Send(new { type = "error", text = error.Message });
            Shutdown();
        }
    }

    [STAThread]
    static void Main(string[] args)
    {
        var output = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };
        try
        {
            if (args.Length < 4) throw new ArgumentException("Invalid Focus Mode pane arguments.");
            var parent = new IntPtr(long.Parse(args[0]));
            if (parent != IntPtr.Zero && !IsWindow(parent)) throw new InvalidOperationException("The HX Edit window is unavailable.");
            if (parent != IntPtr.Zero) SetThreadDpiAwarenessContext(GetWindowDpiAwarenessContext(parent));
            Uri address;
            if (!Uri.TryCreate(args[2], UriKind.Absolute, out address) || address.Scheme != "https")
                throw new ArgumentException("Invalid Focus Mode page address.");
            var hosts = new List<KeyValuePair<string, string>>();
            for (int i = 3; i < args.Length; i++)
            {
                int cut = args[i].IndexOf('=');
                if (cut < 1 || !Directory.Exists(args[i].Substring(cut + 1))) continue;
                hosts.Add(new KeyValuePair<string, string>(args[i].Substring(0, cut), args[i].Substring(cut + 1)));
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (var input = new StreamReader(Console.OpenStandardInput(), Encoding.UTF8))
            using (var pane = new FocusView(parent, args[1], address.AbsoluteUri, hosts, output))
            {
                var handle = pane.Handle;   // a child pane's window exists (hidden) before it is first shown
                WatchParent(parent);
                pane.BeginInvoke(new Action(async () => await pane.Start(input)));
                Application.Run(pane);
            }
        }
        catch (Exception error)
        {
            output.WriteLine(new JavaScriptSerializer().Serialize(new { type = "error", text = error.Message }));
        }
    }
}
