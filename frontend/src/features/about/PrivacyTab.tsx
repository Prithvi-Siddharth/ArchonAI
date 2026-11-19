import { POLICY_UPDATED } from './about-tabs'
import { Bullets, InlineLink, Prose, Section } from './parts'

export function PrivacyTab() {
  return (
    <Prose>
      <Section title="Privacy">
        <p>
          This explains in plain language what this ArchonAI app does with your data. It describes how the software behaves. Whoever runs a server is responsible
          for how they operate it. Last updated {POLICY_UPDATED}.
        </p>
      </Section>
      <Section title="What is stored">
        <Bullets
          items={[
            'Your account: your email address and a salted hash of your password. The password itself is never stored.',
            'Your jobs: the text of each request, its status and timestamps, and the full result. Only your account can open them through the app.',
            <>
              Your provider key, if you add one on <InlineLink to="/byok">Bring Your Own Key</InlineLink>: encrypted before it is stored. The app shows only its last four
              characters and never shows it again.
            </>,
          ]}
        />
      </Section>
      <Section title="What is sent to other services">
        <Bullets
          items={[
            'The AI provider receives your request text and the prompts and answers of the agents working on it. That is Groq by default, or the provider whose key you added. Their own terms and privacy policy apply to what they receive.',
            'If the server turns on AWS CloudWatch, it receives operational logs and metrics such as timings, job IDs, counts and error types. The logs are designed to leave out your request text, generated content and keys.',
          ]}
        />
        <p>Please do not put passwords, secrets, or other people’s personal data in a request.</p>
      </Section>
      <Section title="Cookies and browser storage">
        <Bullets
          items={[
            'One sign-in cookie. It lasts 8 hours, is only sent to the ArchonAI API, and cannot be read by page scripts.',
            'Your theme (light or dark) and whether the sidebar is collapsed, kept in your browser.',
            'No advertising, analytics or tracking cookies, and no third-party trackers.',
          ]}
        />
      </Section>
      <Section title="Who can see your data">
        <p>
          Other users cannot see your jobs, results or settings; another user’s job looks the same as one that does not exist. The person who runs the server can
          access its database, so use a server you trust.
        </p>
      </Section>
      <Section title="Your choices">
        <Bullets
          items={[
            'Remove your provider key at any time. Your jobs then use the server’s provider again.',
            'Sign out to end your session in this browser.',
            'Deleting your account or your jobs is not available in the app yet. Ask whoever runs this server.',
          ]}
        />
      </Section>
    </Prose>
  )
}
