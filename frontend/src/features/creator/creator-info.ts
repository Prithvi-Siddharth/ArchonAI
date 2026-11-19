/** Who built ArchonAI, shown on the Creator page. Edit the values here; nothing else needs to change. */
export interface CreatorInfo {
  name: string
  /** One line under the name. */
  role: string
  email: string
  phone: string
  location: string
  /** Full profile URLs. An empty string hides that button. */
  github: string
  linkedin: string
}

export const CREATOR: CreatorInfo = {
  name: 'Manepalli Prithvi Siddharth',
  role: 'Computer Science undergraduate · AI/ML and AI-powered software engineering',
  email: 'prithvisd.6@gmail.com',
  phone: '+91 7032240742',
  location: 'Hyderabad, Telangana',
  github: 'https://github.com/Prithvi-Siddharth',
  linkedin: 'https://www.linkedin.com/in/prithvi-manepalli-32488a321/',
}
