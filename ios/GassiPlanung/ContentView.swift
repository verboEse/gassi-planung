import SwiftUI

struct ContentView: View {
    @StateObject private var store = WalkStore()

    var body: some View {
        NavigationStack {
            Group {
                if let person = store.person {
                    walkView(person: person)
                } else {
                    loginView
                }
            }
            .navigationTitle("Gassi-Planung")
        }
        .task {
            await store.restoreSession()
        }
        .alert("Gassi-Hinweise", isPresented: $store.isGuidancePresented) {
            Button("Abbrechen", role: .cancel) {
                store.cancelStart()
            }
            Button("Runde starten") {
                Task { await store.confirmStart() }
            }
        } message: {
            Text(store.guidanceMessage)
        }
    }

    private var loginView: some View {
        Form {
            Section("Server") {
                TextField("HTTPS-Serveradresse", text: $store.serverAddress)
                    #if os(iOS)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    #endif
            }
            Section("Anmelden") {
                TextField("Name", text: $store.displayName)
                    #if os(iOS)
                    .textContentType(.username)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    #endif
                SecureField("Passwort", text: $store.password)
                    #if os(iOS)
                    .textContentType(.password)
                    #endif
                Button("Anmelden") {
                    Task { await store.login() }
                }
                .disabled(store.isLoading || store.displayName.isEmpty || store.password.isEmpty)
            }
            Section {
                Text("Melde dich mit deinem bestehenden Gassi-Planungskonto an.")
                    .font(.footnote)
            }
            if let error = store.errorMessage {
                Section {
                    Text(error).foregroundStyle(.red)
                }
            }
        }
    }

    private func walkView(person: WalkPerson) -> some View {
        Form {
            Section {
                HStack {
                    Text("Angemeldet als \(person.name)")
                    Spacer()
                    Button("Abmelden") {
                        Task { await store.logout() }
                    }
                    .disabled(store.isLoading || store.status?.active != nil)
                }
            }

            if let active = store.status?.active {
                Section("Aktive Runde") {
                    Text(store.activeWalkLabel)
                    Text(store.formattedDistance)
                        .font(.system(size: 42, weight: .bold, design: .rounded))
                        .accessibilityLabel("Gesamtstrecke \(store.formattedDistance)")
                    Text("Die Strecke wird auch bei gesperrtem Bildschirm erfasst.")
                        .font(.footnote)

                    if !store.dogs.isEmpty {
                        Text("Hunde")
                            .font(.headline)
                        ForEach(store.dogs) { dog in
                            Toggle(
                                dog.name,
                                isOn: Binding(
                                    get: { store.selectedDogIDs.contains(dog.id) },
                                    set: { selected in
                                        if selected {
                                            store.selectedDogIDs.insert(dog.id)
                                        } else {
                                            store.selectedDogIDs.remove(dog.id)
                                        }
                                    }
                                )
                            )
                        }
                        Text("Wähle mindestens einen Hund für den Abschluss aus.")
                            .font(.footnote)
                    }

                    Button(active.walkType == "extra" ? "Extra-Runde beenden" : "Gassirunde beenden") {
                        Task { await store.endWalk() }
                    }
                    .disabled(store.isLoading)
                }
            } else {
                Section("Gassirunde") {
                    Text(store.currentWindowLabel)
                    if store.canStartPlanned {
                        Button("Geplante Runde starten") {
                            Task { await store.startWalk(extra: false) }
                        }
                        .disabled(store.isLoading)
                    } else if store.status?.window != nil {
                        Text("Diese Runde ist dir nicht zugewiesen. Eine Übernahme kannst du im Plan anfragen.")
                            .font(.footnote)
                    }

                    if store.canStartExtra {
                        Button("Extra-Runde starten") {
                            Task { await store.startWalk(extra: true) }
                        }
                        .disabled(store.isLoading)
                    }
                }
            }

            Section {
                Text("Für die Messung ist Standortzugriff „Immer“ erforderlich. Gespeichert und übertragen wird nur die Gesamtstrecke, keine GPS-Route.")
                    .font(.footnote)
            }

            if let locationError = store.locationTracker.locationError {
                Section {
                    Text(locationError).foregroundStyle(.red)
                }
            }
            if let error = store.errorMessage {
                Section {
                    Text(error).foregroundStyle(.red)
                }
            }
            if let message = store.successMessage {
                Section {
                    Text(message).foregroundStyle(.green)
                }
            }
        }
        .refreshable {
            await store.refresh()
        }
    }
}
